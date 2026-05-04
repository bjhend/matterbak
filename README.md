# matterbak

Back up Mattermost channels of any type with all posts, threads, files, users, emojis.

A note on **personal data**: This script can download personal data of the users like name, nickname, e-mail-address, picture, etc. This may cause legal problems. To avoid that, call the script with option `--skip-users`. You will still find user IDs in the data and which roles/permissions belong to them as channel members but no personal data about the users behind those IDs. The only exception are direct and group channels in the backup, which contain the usernames in the filenames.

Mattermost knows several types of channels:

* Direct channels contain a chat with a single user outside of a team
* Group channels contain a chat with a multiple users outside of a team
* Channels belonging to a team

You can configure for each type which channels should be backed up.

Subsequent runs of the script with the same data dir will update the saved data. So you can run it once to create an initial backup and later update that backup by running it again. If you later add more channels to the configuration those will be downloaded as well. In case you have accidentally deleted part of the files of a channel, delete all channel files and update again. Otherwise updates may get broken.

We implement safe interruption handling: Writes of images and JSON files are protected against partial writes due to interruptions (`Ctrl+C` (SIGINT) and `kill` (SIGTERM) signals). The program delays interruptions while writing to prevent data corruption. After writing finishes, normal interruption behavior resumes and delayed interruptions are called -- you can safely stop the program with `Ctrl+C` or `kill` at any time.

**Attention**: Updating will skip any changes to older posts unless you give option `--update-old-posts`.


## Requirements

The script should work with Python 3.10 or later.
The [mattermost module](https://github.com/someone-somenet-org/mattermost-python-api) is needed for easier API access.

**Note** that we require a version of the mattermost module with additional functions. For some of the additions there are already open [pull requests](https://github.com/someone-somenet-org/mattermost-python-api/issues?q=is%3Aopen%20is%3Apr%20author%3A%40bjhend) to add these to the package.
Until all changes are added to the original mattermost module you have to  use the [`development` branch](https://github.com/bjhend/mattermost-python-api/tree/development) of [this fork](https://github.com/bjhend/mattermost-python-api) containing all required additions.

If you call the script with `uv run` or `poetry run` the required version of the `mattermost` package will be used.


## Configuration

### Credentials

You will need a json config (default name `credentials.json`) with the following format

```json
{
    "user": "my_name",
    "password": "super_secret_pass",
    "url": "https://mattermost.server.org/api"
}
```

Username is the name you have in Mattermost. You can find it by clicking on you avatar in the top right corner
as the name after the `@` sign. Do not include the `@`.

If you login via GitLab or a comparable service, replace `password` wth `token`
and enter the *MMAUTHTOKEN* here. To retrieve it, login via your browser and inspect the cookies for *MMAUTHTOKEN*

1. Open DevTools (F12)
2. Go to Application (Chrome/Edge) or Storage (Firefox)
3. Navigate to Cookies, look at your Mattermost domain

This token will expire and change every time you logout.


### Channels

The channels to back up are configured in another JSON file (default: `channels.json`). It has the following format:

```json
{
    "teams":
    {
        "team1":
        {
            "include": [ "channel1", "channel2", "channel3" ],
            "exclude": [ "channel3" ]
        },

        "team2":
        {
        },

        "team3":
        {
            "exclude": [ "channel4" ]
        }
    },

    "direct":
    [
        "user1",
        "user2"
    ],

    "groups":
    {
        "exact":
        [
            [ "user3", "user4" ]
        ],

        "subset":
        [
            [ "user3", "user5" ]
        ]
    }
}
```

The file has three main keys `teams`, `direct`, and `group` related to the channels types explained above.

`teams` contains a mapping of team names on dicts with the optional keys `include` and `exclude`, which contain a list of channel names each. First, all channels from the `include` list are put on the backup list. If the list is empty or `include` is not given at all, all channels of the team are put on the list. Then, iv `exclude` is present, all channels of the `exclude` list are removed from the backup list.

In this example, `channel1` and `channel2` of `team1` are backed up. `channel3` will be excluded, because exclusion has priority. In addition, all channels of `team2` are backed up as well as finally all channels except `channel4` from `team3`.

`direct` contains a list of user names. Direct chats with these users are backed up.

`groups` may contain two subkeys `exact` and `subset`. Both can contain a list with lists of user names. A list of user names under `exact` selects a group if it has exactly these members besides the user given in the credentials. A list of user names under `subset` selects a group if the configured names are a subset of the members of a group.

In this example the group with exactly `user3`, `user4`, and the credentials user is selected and all groups with at least `user3` and `user5` and eventually other users, provided that such groups exist.


### Command line

Execute matterbak with option `--help` to see the actual command line options:

```
usage: matterbak [-h] [--credentials CREDENTIALS] [--channels CHANNELS] [-d DATA_DIR] [-o OUTPUT_ZIP] [--skip-direct] [--skip-groups] [--skip-teams]
                 [--skip-user-images] [--skip-emojis]

optional arguments:
  -h, --help            show this help message and exit
  --credentials CREDENTIALS
                        json file containing user name, password and server URL, default = credentials.json
  --channels CHANNELS   json file listing all channels to backup, default = channels.json
  -d DATA_DIR, --data-dir DATA_DIR
                        Dir to store downloaded data in, absolute or relative to current dir, default = data
  -o OUTPUT_ZIP, --output-zip OUTPUT_ZIP
                        zip file to write, default is 'matterbak_<user>.zip'
  --update-old-posts    Update also old posts in case they changed since last update
  --skip-direct         skip direct channels
  --skip-groups         skip group channels
  --skip-teams          skip team channels
  --skip-users          Skip storing personal user data (includes --skip-user-images)
  --skip-user-images    Skip storing user images
  --skip-emojis         Skip storing custom emojis
  --rate-limit RATE_LIMIT
                        Max API calls per second. Default: 10. Set to 0 to disable.
  --initial-jitter INITIAL_JITTER
                        Random delay in seconds at script start. Default: 0.
  --step-jitter STEP_JITTER
                        Random delay in seconds between each backup unit. Default: 0.
  --version             show program's version number and exit

```

The script creates folders under the given `--data-dir` for the respective types of data and updates their content on subsequent runs. Finally all data in the *data-dir* is stored in the `--output-zip` file.

The skip options avoid to download the respective data. This may save time if you do not need such data or know that there are no new data of that type on update. You may rerun without the skip option at any time to download that data as well. So we recommend to skip any type of data except one on the first try.

The rate limit and jitter options limit the download rate to avoid overloading the server. Set to sensible values to be fair to the server operator and other users.


## Running

We recommend to use `uv` or `poetry` to run the script. Otherwise install the dependencies defined in `pyproject.toml` manually, see section [Requirements](#Requirements) above.

### Install with uv/poetry

If you are already using uv or poetry for other projects:

```sh
# With uv
uv run matterbak

# With poetry
poetry run matterbak
```

### Install with pipx

`pipx` is the best way to install this tool as it creates an isolated environment automatically, avoiding the need for manual virtual environments.

```sh
# Install the tool directly from GitHub
pipx install "git+https://github.com/michael-behrisch/matterbak.git"
pipx install "git+https://github.com/bjhend/matterbak.git"

# Run the tool
matterbak --help
```

### Install with pip (for development)

```
git clone https://github.com/michael-behrisch/matterbak.git
cd matterbak
pip install -e .
```

## Data

Every Mattermost object has a unique ID. This is always part of the name of the respective file. So if one data file references other data by ID you may easily find the referenced data.

Some files contain binary data. Those are files that were attached to a post as well as images (user images, team icons, custom emojis). These files contain the ID of the object they belong to in their namse.

Team and channel members are stored in a special file, containing a list with all team/channel member objects.

A special case are threads. Threads are not Mattermost objects. To store the threads, any channel data directory contains a threads file with a list of threads. Each thread is a list of post IDs belonging to the same thread. Don't mess up with this file. It will be updated on each run, which may fail if the file is corrupted.


## Notes
There is also another more complete [Python implementation of the mattermost API](https://github.com/Vaelor/python-mattermost-driver) but it
needs more configuration.

The [official API docs](https://api.mattermost.com/) are also available.

## License

MIT
