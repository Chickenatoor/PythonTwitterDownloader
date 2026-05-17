#!/usr/bin/env python3
import http.client as client
from os import getenv
from shutil import which
from urllib.parse import urlparse
from pathlib import Path
import subprocess
import re
import json
import sys

TW_API = "api.fxtwitter.com"
TW_IMG = "pbs.twimg.com"
TW_VID = "video.twimg.com"
RE_TWID = re.compile(r".*?status/([0-9]+).*?")
RE_HEADERS={ "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:149.0) Gecko/20100101 Firefox/149.0", "Connection": "keep-alive"}
#RE_EXT_REQUEST = re.compile(r"https?:\/\/[^\/]*(\/.*)")
#RE_EXT_FNAME = re.compile(r".*\/([a-zA-Z\d\-_]+)\..*")
#RE_EXT_FEXT = re.compile(r".*\/[a-zA-Z\d\-_]+\.([^\?]+).*")

SCRIPT_ROOT = Path(__file__).resolve().parent

class PostInformation:
    def __init__(self, author: str, authorId: int, postId: int, postTimestamp: int, postMedia: list[dict]) -> None:
        self.author = author
        self.authorId = authorId
        self.postId = postId
        self.postTimestamp = postTimestamp
        self.postMedia = postMedia
    def getFilename(self, mediaName: str, mediaIndex: int) -> str:
        return rf"{self.postTimestamp}.{self.author}.{self.authorId}.{self.postId}.{mediaIndex}.{mediaName}"

def promptYesNo():
    while True:
        try:
            resp = input().lower()
        except KeyboardInterrupt:
            print("SIGINT detected. Exiting...")
            exit()
        if(resp == "y"):
            return True
        if(resp == "n"):
            return False

def getDestinationDir() -> str:
    destPath = SCRIPT_ROOT.joinpath("pctwdl-destination.txt")
    if destPath.exists() and destPath.is_dir():
        print(f"Error: \"pctwdl-destination\" is a directory. Please move it.")
        exit(3)
    if not destPath.exists():
        print("File \"pctwdl-destination.txt\" not found. Would you like to specify where the images should be placed? (y/n)")
        if not promptYesNo():
            exit(0)
        print("Please enter your desired directory.")
        pathInp = Path(input()).expanduser()
        if not pathInp.exists():
            print(f"Error: \"{pathInp}\" does not exist.", file = sys.stderr)
            exit(1)
        if not pathInp.is_dir():
            print(f"Error: \"{pathInp}\" is not a directory.", file = sys.stderr)
            exit(1)
        print(f"You have selected \"{pathInp}\" as your destination. Continue? (y/n)")
        if not promptYesNo():
            exit(0)
        pathInpFile = open(destPath, "x")
        pathInpFile.write(str(pathInp))
        pathInpFile.close()
    try:
        destFile = open(destPath, "r")
        ret = destFile.readline().strip()
        destFile.close()
        return ret
    except OSError:
        print("Error: file \"pctwdl-destination.txt\" not found in working directory. Please make one so the script knows where to save media to.", file = sys.stderr)
        exit(1)

def getUrlDebug() -> str:
    urlFile = open(SCRIPT_ROOT.joinpath("samples/imageandvideo.txt"))
    ret = urlFile.readline()
    urlFile.close()
    return ret

def getUrlArgv() -> str | None:
    if(len(sys.argv) != 2):
        return None
    return sys.argv[1]

def getUrlClipboard(hasTermuxApi: bool) -> str:
    if hasTermuxApi:
        request = subprocess.run(["termux-clipboard-get"], capture_output = True)
    elif sys.platform == "win32":
        request = subprocess.run(["powershell.exe", "-NoProfile", "-Command", "Get-Clipboard"], capture_output = True)
    elif getenv("TERMUX_VERSION") is not None:
        print("Error: termux API is not installed.\nUse the command:\npkg install termux-api\nto enable the script to read from clipboard.", file = sys.stderr)
        exit(5)
    else:
        print("Getting clipboard text is not supported outside of termux. Please use args to specify URL", file = sys.stderr)
        exit(5)
    return str(request.stdout)

def getMediaList(postJson: dict) -> list[dict]:
    return postJson["tweet"]["media"]["all"]
def getMediaListVx(postJson: dict) -> list[str]:
    return postJson["media_extended"]

def getPostInformation(postJson: dict, postId: int) -> PostInformation:
    tweet = postJson["tweet"]
    return PostInformation(tweet["author"]["screen_name"],tweet["author"]["id"], postId, tweet["created_timestamp"], tweet["media"]["all"])
def getPostInformationVx(postJson: dict, authorJson: dict, postId: int) -> PostInformation:
    return PostInformation(postJson["user_name"], authorJson["id"], postId, postJson["date_epoch"], postJson["media_extended"])

if __name__ == "__main__":
    hasTermuxApi = None
    cachePath = SCRIPT_ROOT.joinpath("pctwdl-cache.txt")
    if not cachePath.exists():
        cachePath.touch()
    else:
        cacheF = open(cachePath, "r")
        cacheJson = json.load(cacheF)
        cacheF.close()
        hasTermuxApi = cacheJson["is_termux_api"] == True

    if hasTermuxApi == None:
        retCache = dict()
        hasTermuxApi = which("termux-battery-status") is not None
        retCache["is_termux_api"] = hasTermuxApi 
        cacheF = open(cachePath, "w")
        json.dump(retCache, cacheF)

    requestUrl = getUrlArgv()
    if requestUrl == None:
        requestUrl = getUrlClipboard(hasTermuxApi)
    print(requestUrl)
    
    destinationDir = Path(getDestinationDir())
    if not destinationDir.exists():
        print(f"Error: path \"{str(destinationDir)}\" does not exist", file = sys.stderr)
        exit(1)
    if not destinationDir.is_dir():
        print(f"Error: path \"{str(destinationDir)}\" is not a directory", file = sys.stderr)
        exit(1)
    print(f"File destination: \"{destinationDir}\"")

    requestId = None
    matchAttempt = RE_TWID.match(requestUrl)
    if matchAttempt is not None:
        requestId = matchAttempt.groups(1)[0]
    else:
        print("Error: Invalid URL in clipboard", file = sys.stderr)
        exit(2)

    apiConnection = client.HTTPSConnection(TW_API)
    conn = fr"/i/status/{requestId}"
    print(f"CONNECTING TO \"{TW_API}{conn}\"")
    apiConnection.request("GET",conn,headers=RE_HEADERS)
    apiResponse = apiConnection.getresponse()
    if apiResponse.status != 200:
        print(f"Fetching API resulted in an error: {apiResponse.status} ({client.responses[apiResponse.status]})", file = sys.stderr)
        print("The post may either be private, deleted, or does not exist.", file = sys.stderr)
        exit(6)
    postJson = json.loads(apiResponse.read())
    apiConnection.close()
    postInformation = None

    try:
        postInformation = getPostInformation(postJson, int(requestId))
    except KeyError:
        print("Error on getting post information", file = sys.stderr)
        exit(4)

    apiTwImgConnection = None
    apiTwVideoConnection = None
    foundCount = len(postInformation.postMedia)
    successCount = 0
    duplicateCount = 0
    failCount = 0
    successSize = 0
    for i, mediaItem in enumerate(postInformation.postMedia):
        mediaDownloaded = None
        req = urlparse(mediaItem["url"])
        reqPath = Path(req.path)
        mediaFileName = postInformation.getFilename(reqPath.name, i)
        mediaDestinationPath = destinationDir.joinpath(mediaFileName)
        if(mediaDestinationPath.exists()):
            print(f"Warning: file \"{mediaDestinationPath}\" already exists in destination. Skipping", file = sys.stderr)
            duplicateCount += 1
            continue
        if req is None:
            print("Error on parsing mediaItem url", file = sys.stderr)
            failCount += 1
            continue

        if mediaItem["type"] in ["photo", "image"]:
            if apiTwImgConnection is None:
                apiTwImgConnection = client.HTTPSConnection(TW_IMG)
            apiTwImgConnection.request("GET", req.path)
            apiResponse = apiTwImgConnection.getresponse()
            if apiResponse.status != 200:
                print(f"Fetching image resulted in an error: {apiResponse.status} ({client.responses[apiResponse.status]})", file = sys.stderr)
                print("Try again later.", file = sys.stderr)
                failCount += 1
                continue
            mediaDownloaded = apiResponse.read()
        elif mediaItem["type"] in ["video", "gif"]:
            if apiTwVideoConnection == None:
                apiTwVideoConnection = client.HTTPSConnection(TW_VID)
            apiTwVideoConnection.request("GET", req.path)
            apiResponse = apiTwVideoConnection.getresponse()
            if apiResponse.status != 200:
                print(f"Fetching video resulted in an error: {apiResponse.status} ({client.responses[apiResponse.status]})", file = sys.stderr)
                print("Try again later.", file = sys.stderr)
                failCount += 1
                continue
            mediaDownloaded = apiResponse.read()

        if mediaDownloaded is not None and len(mediaDownloaded) > 0:
            print(f"Downloading {mediaFileName} of size {len(mediaDownloaded)}")
            print(f"Writing to \"{mediaDestinationPath}\"")
            writer = open(mediaDestinationPath, "xb")
            writer.write(mediaDownloaded)
            writer.close()
            successCount += 1
            successSize += len(mediaDownloaded)
            if hasTermuxApi:
                subprocess.run(["termux-media-scan", str(mediaDestinationPath)])
        else:
            print(f"Error: Failed to download {mediaFileName}")

    if apiTwImgConnection is not None:
        apiTwImgConnection.close()
    if apiTwVideoConnection is not None:
        apiTwVideoConnection.close()
        
    successStr = f"Successfully downloaded {successCount} out of {foundCount} files. ({successSize/1000000} mb)"
    failStr = ""
    if failCount > 0:
        failStr = failStr + f"Failed to download {failCount} files."
    if duplicateCount > 0:
        if len(failStr) > 0:
            failStr += "\n"
        failStr = failStr + f"Ignored {duplicateCount} duplicate files."
    print(successStr)
    print(failStr)
    if hasTermuxApi:
        subprocess.run(["termux-toast", successStr])
        subprocess.run(["termux-toast", failStr])

