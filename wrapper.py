from telethon.sync import TelegramClient
from telethon.tl.functions.users import GetFullUserRequest
import pickle


# This class contains all the methods to establish a connection with the
# Telegram service using telethon API. It is initialized using a phone
# number associated to a Telegram account.
class TgFuseWrapper:
    # To obtain your Telegram's id and hash,
    # enter https://core.telegram.org/api/obtaining_api_id
    # and follow the steps.
    api_id = None
    api_hash = None

    def __init__(self, number):
        # create and save the client with default api keys
        self.client = TelegramClient('anon', TgFuseWrapper.api_id, TgFuseWrapper.api_hash)
        # start the client
        self.client.start(number)

    # Routine to pin a message in Telegram self-chats
    async def _get_pinned_file(self):
        # WORKAROUND: to get pinned messages in PRIVATE chats
        # get full chat object which contains the pinned message id
        full = await self.client(GetFullUserRequest('me'))
        # get the message from its id
        message = await self.client.get_messages('me', ids=full.pinned_msg_id)
        # get and return the attached file as bytes (None if missing)
        return await self.client.download_media(message, file=bytes)

    # Routine to upload a file into the file system created in your self-chat.
    # It receives as parameters the data of the file, a caption for the file
    # to be uploaded and True or False in case the file already exists and
    # needs to be replaced. The upload contents are force to be in the format
    # of a file document by using force_document=True in the send_file method.
    async def _upload_data(self, data, caption=None, old_to_delete=None):
        # upload given data
        message = await self.client.send_file('me', file=data, caption=caption, force_document=True)
        # if old to delete is provided then try to delete that message
        if old_to_delete is not None:
            await self.delete_data(old_to_delete)
        # return the new message
        return message

    # Routine to delete a message (a file) from a self-chat by its id.
    async def delete_data(self, message_id):
        await self.client.delete_messages('me', message_id)

    # Routine to download the contents of a message (a file) from a self-chat by
    # its id.
    async def _download_data(self, message_id):
        # get message by id from 'me'
        message = await self.client.get_messages('me', ids=message_id)
        # get and return the attached file as bytes (None if missing)
        return await self.client.download_media(message, file=bytes)

    # Routine to write and pin the contents of the superblock file.
    # This routine is used by the mktgfs.py script to set the superblock
    # of the file system.
    async def write_superblock(self, superblock, should_replace=False):
        # WORKAROUND: to get pinned messages in PRIVATE chats
        # if the old superblock should be replaced get its message id, None otherwise
        old_id = (await self.client(GetFullUserRequest('me'))).pinned_msg_id if should_replace else None
        # pickle and save the superblock
        message = await self._pickle_and_save(superblock, 'superblock', old_id)
        # pin the message containing the superblock data
        await message.pin()
        # return the message id
        return message.id

    # Routine to look for the superblock pinned file within the
    # self-chat and deserialize its contents to returned them.
    async def read_superblock(self):
        # get the pinned file if exists, None otherwise
        file = await self._get_pinned_file()
        # the superblock, None as default
        superblock = None
        # if existed
        if file is not None:
            # unpickle the superblock
            superblock = self._unpickle(file)
        # return the superblock or None
        return superblock

    # Routine to write contents into a file. It the file already exists
    # its contents are replaced. It additionally receives the caption
    # of the file.
    async def write_data(self, data, caption=None, old_to_delete=None):
        # pickle and save data then return the message id
        return (await self._pickle_and_save(data, caption, old_to_delete)).id

    # Routine that looks for a file within the self-chats. If the
    # file exists then its contents are deserialized and returned.
    async def read_data(self, message_id):
        # get the file by id
        file = await self._download_data(message_id)
        # the directory data, None as default
        data = None
        # if existed
        if file is not None:
            # unpickle the data
            data = self._unpickle(file)
        # return the retrieved data or None
        return data

    # Routine to serialize a file and saved it into the file system
    # created within the self-chat.
    async def _pickle_and_save(self, obj, caption=None, old_to_delete=None):
        # pickle the given object
        pickled = pickle.dumps(obj)
        # upload the pickled data and return the message
        return await self._upload_data(pickled, caption, old_to_delete)

    # Method to deserialize the contents of a file.
    @staticmethod
    def _unpickle(file):
        # load (maybe changed in case of new serialization method)
        return pickle.loads(file)
