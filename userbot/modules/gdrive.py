# Copyright (C) 2019 The Raphielscape Company LLC.
#
# Licensed under the Raphielscape Public License, Version 1.c (the "License");
# you may not use this file except in compliance with the License.

import asyncio
import math
import os
import time
import json
from pySmartDL import SmartDL
from telethon import events
from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from apiclient.errors import ResumableUploadError
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
from oauth2client import file, client, tools
from userbot import (G_DRIVE_CLIENT_ID, G_DRIVE_CLIENT_SECRET,
                     G_DRIVE_AUTH_TOKEN_DATA, GDRIVE_FOLDER_ID, BOTLOG_CHATID,
                     TEMP_DOWNLOAD_DIRECTORY, CMD_HELP, LOGS)
from userbot.events import register
from userbot.modules.upload_download import humanbytes, time_formatter
from userbot.utils.exceptions import CancelProcess
from userbot.modules.aria import aria2, check_metadata
# =========================================================== #
#                          STATIC                             #
# =========================================================== #
GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.metadata"
]
REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
# global variable to set Folder ID to upload to
parent_id = GDRIVE_FOLDER_ID
# global variable to indicate mimeType of directories in gDrive
G_DRIVE_DIR_MIME_TYPE = "application/vnd.google-apps.folder"


@register(pattern=r"^.gdrive(?: |$)(.*)", outgoing=True)
async def gdrive_upload_function(dryb):
    """ For .gdrive command, upload files to google drive. """
    await dryb.edit("Processing ...")
    input_str = dryb.pattern_match.group(1)
    if CLIENT_ID is None or CLIENT_SECRET is None:
        return
    if not os.path.isdir(TEMP_DOWNLOAD_DIRECTORY):
        os.makedirs(TEMP_DOWNLOAD_DIRECTORY)
        required_file_name = None
    if "|" in input_str:
        url, file_name = input_str.split("|")
        url = url.strip()
        # https://stackoverflow.com/a/761825/4723940
        file_name = file_name.strip()
        head, tail = os.path.split(file_name)
        if head:
            if not os.path.isdir(os.path.join(TEMP_DOWNLOAD_DIRECTORY, head)):
                os.makedirs(os.path.join(TEMP_DOWNLOAD_DIRECTORY, head))
                file_name = os.path.join(head, tail)
        downloaded_file_name = TEMP_DOWNLOAD_DIRECTORY + "" + file_name
        downloader = SmartDL(url, downloaded_file_name, progress_bar=False)
        downloader.start(blocking=False)
        c_time = time.time()
        display_message = None
        while not downloader.isFinished():
            status = downloader.get_status().capitalize()
            total_length = downloader.filesize if downloader.filesize else None
            downloaded = downloader.get_dl_size()
            now = time.time()
            diff = now - c_time
            percentage = downloader.get_progress() * 100
            speed = downloader.get_speed()
            progress_str = "[{0}{1}] {2}%".format(
                ''.join(["▰" for i in range(math.floor(percentage / 10))]),
                ''.join(["▱"
                         for i in range(10 - math.floor(percentage / 10))]),
                round(percentage, 2))
            estimated_total_time = downloader.get_eta(human=True)
            try:
                current_message = (
                    f"URL: {url}\n"
                    "File Name:"
                    f"\n`{file_name}`\n\n"
                    "Status:"
                    f"\n**{status}** | {progress_str} `{percentage}%`"
                    f"\n{humanbytes(downloaded)} of {humanbytes(total_length)}"
                    f" @ {speed}"
                    f"\nETA: {estimated_total_time}"
                )

                if round(diff %
                         10.00) == 0 and current_message != display_message:
                    await dryb.edit(current_message)
                    display_message = current_message
            except Exception as e:
                LOGS.info(str(e))
                pass
        if downloader.isSuccessful():
            await dryb.edit(
                "Downloaded to `{}` successfully !!\nInitiating Upload to Google Drive.."
                .format(downloaded_file_name))
            required_file_name = downloaded_file_name
        else:
            await dryb.edit("Incorrect URL\n{}".format(url))
    elif input_str:
        input_str = input_str.strip()
        if os.path.exists(input_str):
            required_file_name = input_str
            await dryb.edit(
                "Found `{}` in local server, Initiating Upload to Google Drive.."
                .format(input_str))
        else:
            await dryb.edit(
                "File not found in local server. Give me a valid file path !")
            return False
    elif dryb.reply_to_msg_id:
        try:
            c_time = time.time()
            downloaded_file_name = await dryb.client.download_media(
                await dryb.get_reply_message(),
                TEMP_DOWNLOAD_DIRECTORY,
                progress_callback=lambda d, t: asyncio.get_event_loop(
                ).create_task(progress(d, t, gdrive, current_time,
                                       "[FILE - DOWNLOAD]")))
        except Exception as e:
            await dryb.edit(str(e))
        else:
            required_file_name = downloaded_file_name
    try:
        file_name = await get_raw_name(required_file_name)
    except AttributeError:
        reply += (
            "`[ENTRY - ERROR]`\n\n"
            "`Status` : **BAD**\n"
        )
        return reply
    mimeType = await get_mimeType(required_file_name)
    try:
        status = "[FILE - UPLOAD]"
        if isfile(required_file_name):
            try:
                result = await upload(
                    gdrive, service, required_file_name, file_name, mimeType)
            except CancelProcess:
                reply += (
                    "`[FILE - CANCELLED]`\n\n"
                    "`Status` : **OK** - received signal cancelled."
                )
                return reply
            else:
                reply += (
                    f"`{status}`\n\n"
                    f"`Name     :` `{file_name}`\n"
                    f"`Size     :` `{humanbytes(result[0])}`\n"
                    f"`Download :` [{file_name}]({result[1]})\n"
                    "`Status   :` **OK** - Successfully uploaded.\n\n"
                )
                return reply
        else:
            status = status.replace("[FILE", "[FOLDER")
            global parent_Id
            folder = await create_dir(service, file_name)
            parent_Id = folder.get('id')
            try:
                await task_directory(gdrive, service, required_file_name)
            except CancelProcess:
                reply += (
                    "`[FOLDER - CANCELLED]`\n\n"
                    "`Status` : **OK** - received signal cancelled."
                 )
                await reset_parentId()
                return reply
            except Exception:
                await reset_parentId()
            else:
                webViewURL = (
                    "https://drive.google.com/drive/folders/"
                    + parent_Id
                )
                reply += (
                    f"`{status}`\n\n"
                    f"`Name   :` `{file_name}`\n"
                    "`Status :` **OK** - Successfully uploaded.\n"
                    f"`URL    :` [{file_name}]({webViewURL})\n\n"
                )
                await reset_parentId()
                return reply
    except Exception as e:
        status = status.replace("DOWNLOAD]", "ERROR]")
        reply += (
            f"`{status}`\n\n"
            "`Status :` **failed**\n"
            f"`Reason :` `{str(e)}`\n\n"
        )
        return reply
    return


async def download_gdrive(gdrive, service, uri):
    reply = ''
    global is_cancelled
    """ - remove drivesdk and export=download from link - """
    if not isdir(TEMP_DOWNLOAD_DIRECTORY):
        os.mkdir(TEMP_DOWNLOAD_DIRECTORY)
    if "&export=download" in uri:
        uri = uri.split("&export=download")[0]
    elif "file/d/" in uri and "/view" in uri:
        uri = uri.split("?usp=drivesdk")[0]
    try:
        file_Id = uri.split("uc?id=")[1]
    except IndexError:
        try:
            g_drive_link = await upload_file(http, required_file_name,
                                             file_name, mime_type, dryb,
                                             parent_id)
            await dryb.edit(
                f"File: `{required_file_name}`\n"
                f"was Successfully Uploaded to [Google Drive]({g_drive_link})!"
            )
        except Exception as e:
            await dryb.edit(
                f"Error while Uploading to Google Drive\nError Code:\n`{e}`")


@register(pattern=r"^.ggd(?: |$)(.*)", outgoing=True)
async def upload_dir_to_gdrive(event):
    await event.edit("Processing ...")
    if CLIENT_ID is None or CLIENT_SECRET is None:
        return
    input_str = event.pattern_match.group(1)
    if os.path.isdir(input_str):
        # TODO: remove redundant code
        if G_DRIVE_AUTH_TOKEN_DATA is not None:
            with open(G_DRIVE_TOKEN_FILE, "w") as t_file:
                t_file.write(G_DRIVE_AUTH_TOKEN_DATA)
        # Check if token file exists, if not create it by requesting authorization code
        storage = None
        if not os.path.isfile(G_DRIVE_TOKEN_FILE):
            storage = await create_token_file(G_DRIVE_TOKEN_FILE, event)
        http = authorize(G_DRIVE_TOKEN_FILE, storage)
        # Authorize, get file parameters, upload file and print out result URL for download
        # first, create a sub-directory
        dir_id = await create_directory(
            http, os.path.basename(os.path.abspath(input_str)), parent_id)
        await DoTeskWithDir(http, input_str, event, dir_id)
        dir_link = "https://drive.google.com/folderview?id={}".format(dir_id)
        await event.edit(f"Here is your Google Drive [link]({dir_link})")
    else:
        await event.edit(f"Directory {input_str} does not seem to exist")
            file_name = re.search(
                'filename="(.*)"', download.headers["Content-Disposition"]
            ).group(1)
            file_path = TEMP_DOWNLOAD_DIRECTORY + file_name
            with io.FileIO(file_path, 'wb') as files:
                CHUNK_SIZE = None
                current_time = time.time()
                display_message = None
                first = True
                is_cancelled = False
                for chunk in download.iter_content(CHUNK_SIZE):
                    if is_cancelled is True:
                        raise CancelProcess

                    if not chunk:
                        break

                    diff = time.time() - current_time
                    if first is True:
                        downloaded = len(chunk)
                        first = False
                    else:
                        downloaded += len(chunk)
                    percentage = downloaded / file_size * 100
                    speed = round(downloaded / diff, 2)
                    eta = round((file_size - downloaded) / speed)
                    prog_str = "`Downloading...` | [{0}{1}] `{2}%`".format(
                        "".join(["●" for i in range(
                                math.floor(percentage / 10))]),
                        "".join(["○"for i in range(
                                10 - math.floor(percentage / 10))]),
                        round(percentage, 2))
                    current_message = (
                        "`[FILE - DOWNLOAD]`\n\n"
                        f"`Name` : `{file_name}`\n"
                        f"`Status`\n{prog_str}\n"
                        f"`{humanbytes(downloaded)} of {humanbytes(file_size)}"
                        f" @ {humanbytes(speed)}`\n"
                        f"`ETA` -> {time_formatter(eta)}"
                    )
                    if round(
                      diff % 10.00) == 0 and (display_message
                                              != current_message) or (
                      downloaded == file_size):
                        await gdrive.edit(current_message)
                        display_message = current_message
                    files.write(chunk)
    else:
        file_name = file.get('name')
        mimeType = file.get('mimeType')
        if mimeType == 'application/vnd.google-apps.folder':
            return await gdrive.edit("`Aborting, folder download not support`")
        file_path = TEMP_DOWNLOAD_DIRECTORY + file_name
        request = service.files().get_media(fileId=file_Id)
        with io.FileIO(file_path, 'wb') as df:
            downloader = MediaIoBaseDownload(df, request)
            complete = False
            is_cancelled = False
            current_time = time.time()
            display_message = None
            while complete is False:
                if is_cancelled is True:
                    raise CancelProcess

                status, complete = downloader.next_chunk()
                if status:
                    file_size = status.total_size
                    diff = time.time() - current_time
                    downloaded = status.resumable_progress
                    percentage = downloaded / file_size * 100
                    speed = round(downloaded / diff, 2)
                    eta = round((file_size - downloaded) / speed)
                    prog_str = "`Downloading...` | [{0}{1}] `{2}%`".format(
                        "".join(["●" for i in range(
                                math.floor(percentage / 10))]),
                        "".join(["○" for i in range(
                                10 - math.floor(percentage / 10))]),
                        round(percentage, 2))
                    current_message = (
                        "`[FILE - DOWNLOAD]`\n\n"
                        f"`Name` : `{file_name}`\n"
                        f"`Status`\n{prog_str}\n"
                        f"`{humanbytes(downloaded)} of {humanbytes(file_size)}"
                        f" @ {humanbytes(speed)}`\n"
                        f"`ETA` -> {time_formatter(eta)}"
                    )
                    if display_message != current_message or (
                      downloaded == file_size):
                        await gdrive.edit(current_message)
                        display_message = current_message
    await gdrive.edit(
        "`[FILE - DOWNLOAD]`\n\n"
        f"`Name   :` `{file_name}`\n"
        f"`Size   :` `{humanbytes(file_size)}`\n"
        f"`Path   :` `{file_path}`\n"
        "`Status :` **OK** - Successfully downloaded."
    )
    msg = await gdrive.respond("`Answer the question in your BOTLOG group`")
    async with gdrive.client.conversation(BOTLOG_CHATID) as conv:
        ask = await conv.send_message("`Proceed with mirroring? [y/N]`")
        try:
            r = conv.wait_event(
              events.NewMessage(outgoing=True, chats=BOTLOG_CHATID))
            r = await r
        except Exception:
            ans = 'N'
        else:
            ans = r.message.message.strip()
            await gdrive.client.delete_messages(BOTLOG_CHATID, r.id)
        await gdrive.client.delete_messages(gdrive.chat_id, msg.id)
        await gdrive.client.delete_messages(BOTLOG_CHATID, ask.id)
    if ans.capitalize() == 'N':
        return reply
    elif ans.capitalize() == "Y":
        try:
            result = await upload(
                gdrive, service, file_path, file_name, mimeType)
        except CancelProcess:
            reply += (
                "`[FILE - CANCELLED]`\n\n"
                "`Status` : **OK** - received signal cancelled."
            )
        else:
            reply += (
                "`[FILE - UPLOAD]`\n\n"
                f"`Name     :` `{file_name}`\n"
                f"`Size     :` `{humanbytes(result[0])}`\n"
                f"`Download :` [{file_name}]({result[1]})\n"
                "`Status   :` **OK**\n\n"
            )
        return reply
    else:
        await set.edit(
            "Use `.gdrivesp <link to GDrive Folder>` to set the folder to upload new files to."
        )


@register(pattern="^.gsetclear$", outgoing=True)
async def download(gclr):
    """For .gsetclear command, allows you clear ur curnt custom path"""
    await gclr.reply("Processing ...")
    parent_id = GDRIVE_FOLDER_ID
    await gclr.edit("Custom Folder ID cleared successfully.")


@register(pattern="^.gfolder$", outgoing=True)
async def show_current_gdrove_folder(event):
    if parent_id:
        folder_link = f"https://drive.google.com/drive/folders/" + parent_id
        await event.edit(
            f"My userbot is currently uploading files [here]({folder_link})")
    else:
        await event.edit(
            "My userbot is currently uploading files to the root of my Google Drive storage."
            "\nFind uploaded files [here](https://drive.google.com/drive/my-drive)"
        )


# Get mime type and name of given file
def file_ops(file_path):
    mime_type = guess_type(file_path)[0]
    mime_type = mime_type if mime_type else "text/plain"
    file_name = file_path.split("/")[-1]
    return file_name, mime_type


async def create_token_file(token_file, event):
    # Run through the OAuth flow and retrieve credentials
    flow = OAuth2WebServerFlow(CLIENT_ID,
                               CLIENT_SECRET,
                               OAUTH_SCOPE,
                               redirect_uri=REDIRECT_URI)
    authorize_url = flow.step1_get_authorize_url()
    async with event.client.conversation(BOTLOG_CHATID) as conv:
        await conv.send_message(
            f"Go to the following link in your browser: {authorize_url} and reply the code"
        )
        response = conv.wait_event(
            events.NewMessage(outgoing=True, chats=BOTLOG_CHATID))
        response = await response
        code = response.message.message.strip()
        credentials = flow.step2_exchange(code)
        storage = Storage(token_file)
        storage.put(credentials)
        return storage


def authorize(token_file, storage):
    # Get credentials
    if storage is None:
        storage = Storage(token_file)
    credentials = storage.get()
    # Create an httplib2.Http object and authorize it with our credentials
    http = httplib2.Http()
    try:
        http.redirect_codes = http.redirect_codes - {308}
    except AttributeError:
        pass
    credentials.refresh(http)
    http = credentials.authorize(http)
    return http


async def upload_file(http, file_path, file_name, mime_type, event, parent_id):
    # Create Google Drive service instance
    drive_service = build("drive", "v2", http=http, cache_discovery=False)
    # File body description
    media_body = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)
    body = {
        "title": file_name,
        "description": "Uploaded from Telegram using userbot.",
        "mimeType": mime_type,
    }
    try:
        if parent_Id is not None:
            pass
    except NameError:
        """ - Fallback to G_DRIVE_FOLDER_ID else root dir - """
        if G_DRIVE_FOLDER_ID is not None:
            body['parents'] = [G_DRIVE_FOLDER_ID]
    else:
        """ - Override G_DRIVE_FOLDER_ID because parent_Id not empty - """
        body['parents'] = [parent_Id]
    media_body = MediaFileUpload(
        file_path,
        mimetype=mimeType,
        resumable=True
    )
    """ - Start upload process - """
    file = service.files().create(body=body, media_body=media_body,
                                  fields="id, size, webContentLink")
    global is_cancelled
    current_time = time.time()
    response = None
    display_message = None
    is_cancelled = False
    while response is None:
        if is_cancelled is True:
            raise CancelProcess

        status, response = file.next_chunk()
        await asyncio.sleep(1)
        if status:
            percentage = int(status.progress() * 100)
            progress_str = "[{0}{1}] {2}%".format(
                "".join(["▰" for i in range(math.floor(percentage / 10))]),
                "".join(["▱"
                         for i in range(10 - math.floor(percentage / 10))]),
                round(percentage, 2))
            current_message = (
                f"Uploading to Google Drive\n"
                f"File Name: {file_name}\n{progress_str}"
            )
            if display_message != current_message:
                try:
                    await event.edit(current_message)
                    display_message = current_message
                except Exception as e:
                    LOGS.info(str(e))
                    pass
    file_id = response.get("id")
    file_size = response.get("size")
    downloadURL = response.get("webContentLink")
    """ - Change permission - """
    try:
        await change_permission(service, file_id)
    except Exception:
        pass
    return int(file_size), downloadURL


async def task_directory(gdrive, service, folder_path):
    global parent_Id
    global is_cancelled
    is_cancelled = False
    lists = os.listdir(folder_path)
    if len(lists) == 0:
        return parent_Id
    root_parent_Id = None
    for f in lists:
        if is_cancelled is True:
            raise CancelProcess

        current_f_name = join(folder_path, f)
        if isdir(current_f_name):
            folder = await create_dir(service, f)
            parent_Id = folder.get('id')
            root_parent_Id = await task_directory(gdrive,
                                                  service, current_f_name)
        else:
            file_name, mime_type = file_ops(current_file_name)
            # current_file_name will have the full path
            g_drive_link = await upload_file(http, current_file_name,
                                             file_name, mime_type, event,
                                             parent_id)
            r_p_id = parent_id
    # TODO: there is a #bug here :(
    return r_p_id


async def gdrive_list_file_md(service, file_id):
    try:
        file = service.files().get(fileId=file_id).execute()
        # LOGS.info(file)
        file_meta_data = {}
        file_meta_data["title"] = file["title"]
        mimeType = file["mimeType"]
        file_meta_data["createdDate"] = file["createdDate"]
        if mimeType == G_DRIVE_DIR_MIME_TYPE:
            # is a dir.
            file_meta_data["mimeType"] = "directory"
            file_meta_data["previewURL"] = file["alternateLink"]
        else:
            # is a file.
            file_meta_data["mimeType"] = file["mimeType"]
            file_meta_data["md5Checksum"] = file["md5Checksum"]
            file_meta_data["fileSize"] = str(humanbytes(int(file["fileSize"])))
            file_meta_data["quotaBytesUsed"] = str(
                humanbytes(int(file["quotaBytesUsed"])))
            file_meta_data["previewURL"] = file["downloadUrl"]
        return json.dumps(file_meta_data, sort_keys=True, indent=4)
    except Exception as e:
        return str(e)


async def gdrive_search(http, search_query):
    if parent_id:
        query = "'{}' in parents and (title contains '{}')".format(
            parent_id, search_query)
    else:
        query = "title contains '{}'".format(search_query)
    drive_service = build("drive", "v2", http=http, cache_discovery=False)
    page_token = None
    res = ""
    while True:
        try:
            response = drive_service.files().list(
                q=query,
                spaces="drive",
                fields="nextPageToken, items(id, title, mimeType)",
                pageToken=page_token).execute()
            for file in response.get("items", []):
                file_title = file.get("title")
                file_id = file.get("id")
                if file.get("mimeType") == G_DRIVE_DIR_MIME_TYPE:
                    res += f"`[FOLDER] {file_title}`\nhttps://drive.google.com/drive/folders/{file_id}\n\n"
                else:
                    res += f"`{file_title}`\nhttps://drive.google.com/uc?id={file_id}&export=download\n\n"
            page_token = response.get("nextPageToken", None)
            if page_token is None:
                break

            file_name = files.get('name')
            file_id = files.get('id')
            if files.get('mimeType') == 'application/vnd.google-apps.folder':
                link = files.get('webViewLink')
                message += (
                    f"`[FOLDER]` - `{file_id}`\n"
                    f"`{file_name}`\n{link}\n\n"
                )
            else:
                link = files.get('webContentLink')
                message += (
                    f"`[FILE]` - `{file_id}`\n"
                    f"`{file_name}`\n{link}\n\n"
                )
            result.append(files)
        if len(result) >= page_size:
            break

        page_token = response.get('nextPageToken', None)
        if page_token is None:
            break

    del result
    if query == '':
        query = 'Not specified'
    if len(message) > 4096:
        await gdrive.edit("`Result is too big, sending it as file...`")
        with open('result.txt', 'w') as r:
            r.write(
                f"Google Drive Query:\n{query}\n\nResults\n\n{message}")
        await gdrive.client.send_file(
            gdrive.chat_id,
            'result.txt',
            caption='Google Drive Query List.'
        )
    else:
        await gdrive.edit(
            "**Google Drive Query**:\n"
            f"`{query}`\n\n**Results**\n\n{message}")
    return


@register(pattern="^.gdf (mkdir|rm|chck) (.*)", outgoing=True)
async def google_drive_managers(gdrive):
    """ - Google Drive folder/file management - """
    await gdrive.edit("`Sending information...`")
    service = await create_app(gdrive)
    if service is False:
        return
    """ - Split name if contains spaces by using ; - """
    f_name = gdrive.pattern_match.group(2).split(';')
    exe = gdrive.pattern_match.group(1)
    reply = ''
    for name_or_id in f_name:
        """ - in case given name has a space beetween ; - """
        name_or_id = name_or_id.strip()
        metadata = {
            'name': name_or_id,
            'mimeType': 'application/vnd.google-apps.folder',
        }
        try:
            if parent_Id is not None:
                pass
        except NameError:
            """ - Fallback to G_DRIVE_FOLDER_ID else to root dir - """
            if G_DRIVE_FOLDER_ID is not None:
                metadata['parents'] = [G_DRIVE_FOLDER_ID]
        else:
            """ - Override G_DRIVE_FOLDER_ID because parent_Id not empty - """
            metadata['parents'] = [parent_Id]
        page_token = None
        result = service.files().list(
            q=f'name="{name_or_id}"',
            spaces='drive',
            fields=(
                'nextPageToken, files(parents, name, id, size, '
                'mimeType, webViewLink, webContentLink, description)'
            ),
            pageToken=page_token
        ).execute()
        if exe == "mkdir":
            """
            - Create a directory, abort if exist when parent not given -
            """
            status = "[FOLDER - EXIST]"
            try:
                folder = result.get('files', [])[0]
            except IndexError:
                folder = await create_dir(service, name_or_id)
                status = status.replace("EXIST]", "CREATED]")
            folder_id = folder.get('id')
            webViewURL = folder.get('webViewLink')
            if "CREATED" in status:
                """ - Change permission - """
                try:
                    await change_permission(service, folder_id)
                except Exception:
                    pass
            reply += (
                f"`{status}`\n\n"
                f"`Name :` `{name_or_id}`\n"
                f"`ID   :` `{folder_id}`\n"
                f"`URL  :` [Open]({webViewURL})\n\n"
            )
        elif exe == "rm":
            """ - Permanently delete, skipping the trash - """
            try:
                """ - Try if given value is a name not a folderId/fileId - """
                f = result.get('files', [])[0]
                f_id = f.get('id')
            except IndexError:
                """ - If failed assumming value is folderId/fileId - """
                f_id = name_or_id
                try:
                    f = await get_information(service, f_id)
                except Exception as e:
                    reply += (
                        f"`[FILE/FOLDER - ERROR]`\n\n"
                        f"`Status` : `{str(e)}`\n\n"
                    )
                    continue
            name = f.get('name')
            mimeType = f.get('mimeType')
            if mimeType == 'application/vnd.google-apps.folder':
                status = "[FOLDER - DELETE]"
            else:
                status = "[FILE - DELETE]"
            try:
                service.files().delete(fileId=f_id).execute()
            except HttpError as e:
                status.replace("DELETE]", "ERROR]")
                reply += (
                    f"`{status}`\n\n"
                    f"`Status` : `{str(e)}`\n\n"
                )
                continue
            else:
                reply += (
                    f"`{status}`\n\n"
                    f"`Name   :` `{name}`\n"
                    "`Status :` `OK`\n\n"
                )
        elif exe == "chck":
            """ - Check file/folder if exists - """
            try:
                f = result.get('files', [])[0]
            except IndexError:
                """ - If failed assumming value is folderId/fileId - """
                f_id = name_or_id
                try:
                    f = await get_information(service, f_id)
                except Exception as e:
                    reply += (
                        "`[FILE/FOLDER - ERROR]`\n\n"
                        "`Status :` **BAD**\n"
                        f"`Reason :` `{str(e)}`\n\n"
                    )
                    continue
            """ - If exists parse file/folder information - """
            name_or_id = f.get('name')  # override input value
            f_id = f.get('id')
            f_size = f.get('size')
            mimeType = f.get('mimeType')
            webViewLink = f.get('webViewLink')
            downloadURL = f.get('webContentLink')
            description = f.get('description')
            if mimeType == "application/vnd.google-apps.folder":
                status = "[FOLDER - EXIST]"
            else:
                status = "[FILE - EXIST]"
            msg = (
                f"`{status}`\n\n"
                f"`Name     :` `{name_or_id}`\n"
                f"`ID       :` `{f_id}`\n"
            )
            if mimeType != "application/vnd.google-apps.folder":
                msg += f"`Size     :` `{humanbytes(f_size)}`\n"
                msg += f"`Download :` [{name_or_id}]({downloadURL})\n\n"
            else:
                msg += f"`URL      :` [Open]({webViewLink})\n\n"
            if description:
                msg += f"`About    :`\n`{description}`\n\n"
            reply += msg
        page_token = result.get('nextPageToken', None)
    await gdrive.edit(reply)
    return


@register(pattern="^.gdabort(?: |$)", outgoing=True)
async def cancel_process(gdrive):
    """
       Abort process for download and upload
    """
    global is_cancelled
    downloads = aria2.get_downloads()
    await gdrive.edit("`Cancelling...`")
    if len(downloads) != 0:
        aria2.remove_all(force=True)
        aria2.autopurge()
    is_cancelled = True
    await asyncio.sleep(3.5)
    await gdrive.delete()


@register(pattern="^.gd(?: |$)(.*)", outgoing=True)
async def google_drive(gdrive):
    reply = ''
    """ - Parsing all google drive function - """
    value = gdrive.pattern_match.group(1)
    file_path = None
    uri = None
    if not value and not gdrive.reply_to_msg_id:
        return
    elif value and gdrive.reply_to_msg_id:
        return await gdrive.edit(
            "`[UNKNOWN - ERROR]`\n\n"
            "`Status :` **failed**\n"
            "`Reason :` Confused to upload file or the replied message/media."
        )
    service = await create_app(gdrive)
    if service is False:
        return
    if isfile(value):
        file_path = value
        if file_path.endswith(".torrent"):
            uri = [file_path]
            file_path = None
    elif isdir(value):
        folder_path = value
        global parent_Id
        folder_name = await get_raw_name(folder_path)
        folder = await create_dir(service, folder_name)
        parent_Id = folder.get('id')
        try:
            await task_directory(gdrive, service, folder_path)
        except CancelProcess:
            await gdrive.respond(
                "`[FOLDER - CANCELLED]`\n\n"
                "`Status` : **OK** - received signal cancelled."
            )
            await reset_parentId()
            return await gdrive.delete()
        except Exception as e:
            await gdrive.edit(
                "`[FOLDER - UPLOAD]`\n\n"
                f"`Name   :` `{folder_name}`\n"
                "`Status :` **BAD**\n"
                f"`Reason :` {str(e)}"
            )
            return await reset_parentId()
        else:
            webViewURL = "https://drive.google.com/drive/folders/" + parent_Id
            await gdrive.edit(
                "`[FOLDER - UPLOAD]`\n\n"
                f"`Name   :` `{folder_name}`\n"
                "`Status :` **OK** - Successfully uploaded.\n"
                f"`URL    :` [{folder_name}]({webViewURL})\n"
            )
            return await reset_parentId()
    elif not value and gdrive.reply_to_msg_id:
        reply += await download(gdrive, service)
        await gdrive.respond(reply)
        return await gdrive.delete()
    else:
        if re.findall(r'\bhttps?://drive\.google\.com\S+', value):
            """ - Link is google drive fallback to download - """
            value = re.findall(r'\bhttps?://drive\.google\.com\S+', value)
            for uri in value:
                try:
                    reply += await download_gdrive(gdrive, service, uri)
                except CancelProcess:
                    reply += (
                        "`[FILE - CANCELLED]`\n\n"
                        "`Status` : **OK** - received signal cancelled."
                    )
                    break
                except Exception as e:
                    reply += (
                        "`[FILE - ERROR]`\n\n"
                        "`Status :` **BAD**\n"
                        f"`Reason :` {str(e)}\n\n"
                    )
                    continue
            if reply:
                await gdrive.respond(reply, link_preview=False)
                return await gdrive.delete()
            else:
                return
        elif re.findall(r'\bhttps?://.*\.\S+', value) or "magnet:?" in value:
            uri = value.split()
        else:
            for fileId in value.split():
                if any(map(str.isdigit, fileId)):
                    one = True
                else:
                    one = False
                if "-" in fileId or "_" in fileId:
                    two = True
                else:
                    two = False
                if True in [one or two]:
                    try:
                        reply += await download_gdrive(gdrive, service, fileId)
                    except CancelProcess:
                        reply += (
                            "`[FILE - CANCELLED]`\n\n"
                            "`Status` : **OK** - received signal cancelled."
                        )
                        break
                    except Exception as e:
                        reply += (
                            "`[FILE - ERROR]`\n\n"
                            "`Status :` **BAD**\n"
                            f"`Reason :` {str(e)}\n\n"
                        )
                        continue
            if reply:
                await gdrive.respond(reply, link_preview=False)
                return await gdrive.delete()
            else:
                return
        if not uri and not gdrive.reply_to_msg_id:
            return await gdrive.edit(
                "`[VALUE - ERROR]`\n\n"
                "`Status :` **BAD**\n"
                "`Reason :` given value is not URL nor file/folder path.\n"
                "If you think this is wrong, maybe you use .gd with multiple "
                "value of files/folders, e.g `.gd <filename1> <filename2>` "
                "for upload from files/folders path this doesn't support it."
            )
    if uri and not gdrive.reply_to_msg_id:
        for dl in uri:
            try:
                reply += await download(gdrive, service, dl)
            except Exception as e:
                if " not found" in str(e) or "'file'" in str(e):
                    reply += (
                        "`[FILE - CANCELLED]`\n\n"
                        "`Status` : **OK** - received signal cancelled."
                    )
                    await asyncio.sleep(2.5)
                    break
                else:
                    """ - if something bad happened, continue to next uri - """
                    reply += (
                        "`[UNKNOWN - ERROR]`\n\n"
                        "`Status :` **BAD**\n"
                        f"`Reason :` `{dl}` | `{str(e)}`\n\n"
                    )
                    continue
        await gdrive.respond(reply, link_preview=False)
        return await gdrive.delete()
    mimeType = await get_mimeType(file_path)
    file_name = await get_raw_name(file_path)
    try:
        result = await upload(gdrive, service,
                              file_path, file_name, mimeType)
    except CancelProcess:
        gdrive.respond(
            "`[FILE - CANCELLED]`\n\n"
            "`Status` : **OK** - received signal cancelled."
        )
    if result:
        await gdrive.respond(
            "`[FILE - UPLOAD]`\n\n"
            f"`Name     :` `{file_name}`\n"
            f"`Size     :` `{humanbytes(result[0])}`\n"
            f"`Download :` [{file_name}]({result[1]})\n"
            "`Status   :` **OK** - Successfully uploaded.\n",
            link_preview=False
            )
    await gdrive.delete()
    return


@register(pattern="^.gdfset (put|rm)(?: |$)(.*)", outgoing=True)
async def set_upload_folder(gdrive):
    """ - Set parents dir for upload/check/makedir/remove - """
    await gdrive.edit("`Sending information...`")
    global parent_Id
    exe = gdrive.pattern_match.group(1)
    if exe == "rm":
        if G_DRIVE_FOLDER_ID is not None:
            parent_Id = G_DRIVE_FOLDER_ID
            return await gdrive.edit(
                "`[FOLDER - SET]`\n\n"
                "`Status` : **OK** - using `G_DRIVE_FOLDER_ID` now."
            )
        else:
            try:
                del parent_Id
            except NameError:
                return await gdrive.edit(
                    "`[FOLDER - SET]`\n\n"
                    "`Status` : **BAD** - No parent_Id is set."
                )
            else:
                return await gdrive.edit(
                    "`[FOLDER - SET]`\n\n"
                    "`Status` : **OK**"
                    " - `G_DRIVE_FOLDER_ID` empty, will use root."
                )
    inp = gdrive.pattern_match.group(2)
    if not inp:
        return await gdrive.edit(">`.gdfset put <folderURL/folderID>`")
    """ - Value for .gdfset (put|rm) can be folderId or folder link - """
    try:
        ext_id = re.findall(r'\bhttps?://drive\.google\.com\S+', inp)[0]
    except IndexError:
        """ - if given value isn't folderURL assume it's an Id - """
        if any(map(str.isdigit, inp)):
            c1 = True
        else:
            c1 = False
        if "-" in inp or "_" in inp:
            c2 = True
        else:
            c2 = False
        if True in [c1 or c2]:
            parent_Id = inp
            return await gdrive.edit(
                "`[PARENT - FOLDER]`\n\n"
                "`Status` : **OK** - Successfully changed."
            )
        else:
            await gdrive.edit(
                "`[PARENT - FOLDER]`\n\n"
                "`Status` : **WARNING** - forcing use..."
            )
            parent_Id = inp
    else:
        if "uc?id=" in ext_id:
            return await gdrive.edit(
                "`[URL - ERROR]`\n\n"
                "`Status` : **BAD** - Not a valid folderURL."
            )
        try:
            parent_Id = ext_id.split("folders/")[1]
        except IndexError:
            """ - Try catch again if URL open?id= - """
            try:
                parent_Id = ext_id.split("open?id=")[1]
            except IndexError:
                if "/view" in ext_id:
                    parent_Id = ext_id.split("/")[-2]
                else:
                    try:
                        parent_Id = ext_id.split("folderview?id=")[1]
                    except IndexError:
                        return await gdrive.edit(
                            "`[URL - ERROR]`\n\n"
                            "`Status` : **BAD** - Not a valid folderURL."
                        )
        await gdrive.edit(
                "`[PARENT - FOLDER]`\n\n"
                "`Status` : **OK** - Successfully changed."
        )
    return


async def check_progress_for_dl(gdrive, gid, previous):
    complete = None
    global is_cancelled
    global filenames
    is_cancelled = False
    while not complete:
        if is_cancelled is True:
            raise CancelProcess

        file = aria2.get_download(gid)
        complete = file.is_complete
        try:
            filenames = file.name
        except IndexError:
            pass
        try:
            if not complete and not file.error_message:
                percentage = int(file.progress)
                downloaded = percentage * int(file.total_length) / 100
                prog_str = "`Downloading...` | [{0}{1}] `{2}`".format(
                    "".join(["●" for i in range(
                            math.floor(percentage / 10))]),
                    "".join(["○" for i in range(
                            10 - math.floor(percentage / 10))]),
                    file.progress_string())
                msg = (
                    "`[URI - DOWNLOAD]`\n\n"
                    f"`Name` : `{file.name}`\n"
                    f"`Status` -> **{file.status.capitalize()}**\n"
                    f"{prog_str}\n"
                    f"`{humanbytes(downloaded)} of"
                    f" {file.total_length_string()}"
                    f" @ {file.download_speed_string()}`\n"
                    f"`ETA` -> {file.eta_string()}\n"
                )
                if msg != previous or downloaded == file.total_length_string():
                    await gdrive.edit(msg)
                    msg = previous
            else:
                await gdrive.edit(f"`{msg}`")
            await asyncio.sleep(5)
            await check_progress_for_dl(gdrive, gid, previous)
            file = aria2.get_download(gid)
            complete = file.is_complete
            if complete:
                return await gdrive.edit(f"`{file.name}`\n\n"
                                         "Successfully downloaded...")
        except Exception as e:
            if " depth exceeded" in str(e):
                file.remove(force=True)
                try:
                    await gdrive.edit(
                        "`[URI - DOWNLOAD]`\n\n"
                        f"`Name   :` `{file.name}`\n"
                        "`Status :` **failed**\n"
                        "`Reason :` Auto cancelled download, URI/Torrent dead."
                    )
                except Exception:
                    pass


CMD_HELP.update({
    "gdrive":
    ">`.gdrive <file_path/reply/URL|file_name>`"
    "\nUsage: Uploads the file in reply , URL or file path in server to your GoogleDrive."
    "\n\n>`.gsetf <Folder ID GoogleDrive>`"
    "\nUsage: Sets the folder to upload new files to."
    "\n\n>`.gsetclear`"
    "\nUsage: Reverts to default upload destination."
    "\n\n>`.gfolder`"
    "\nUsage: Shows your current upload destination/folder."
    "\n\n>`.list <query>`"
    "\nUsage: Looks for files and folders in your GoogleDrive."
    "\n\n>`.ggd <path_to_folder_in_server>`"
    "\nUsage: Uploads all the files in the directory to a folder in GoogleDrive."
})
