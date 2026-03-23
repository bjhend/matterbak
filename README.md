# matterbak
Backing up mattermost channels (including files) and users

## Requirements
The script should work with Python 3.7 or later.
The [mattermost module](https://github.com/someone-somenet-org/mattermost-python-api) is needed for easier API access.
It can be installed using `pip install mattermost`.

## Usage
You will need a json config (default name "credentials.json") of the following format
```
{
    "user": "my_name",
    "password": "super_secret_pass",
    "url": "https://mattermost.server.org/api"
}
```
or if you login via GitLab or a comparable service, replace "password" wth "token"
and enter the MMAUTHTOKEN here. To retrieve it, login via your browser and inspect the cookies for MMAUTHTOKEN
1. Open DevTools (F12)
2. Go to Application (Chrome/Edge) or Storage (Firefox)
3. Navigate to Cookies, look at your Mattermost domain

This token will expire and change every time you logout.

You can either install the script using `pip install .` in a clone of the repo or just call the script directly.

A call to `matterbak` (installed version) or `matterbak.py` will then retrieve all teams and channels the user
mentioned in the credentials file is a member of and will then dump the posts and files from all those channels.
If you want to exclude channels by their name use `-x <channel1> [<channel2> ...]`.
If you want to include channels by their name use `-i <channel1> [<channel2> ...]`.

If you want to backup for a different user you can use the `--backup-user <user_name>` option but you will
need the privileges to access the data of this user.

The script creates three folders "teams", "channels" and "users" which contain the data in json files.
The "channels" folder contains a subfolder for each channel with the posts and files from the channel.
The backup is incrementally in the sense that existing posts and users are not overwritten (and not updated!)
In the end the content of all three folders is zipped into a single file.

## Notes
There is also another more complete [Python implementation of the mattermost API](https://github.com/Vaelor/python-mattermost-driver) but it
needs more configuration.

The [official API docs](https://api.mattermost.com/) are also available.

## License

MIT
