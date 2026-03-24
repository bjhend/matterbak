# matterbak

Back up Mattermost channels of any type with all posts and files and their users.

Mattermost knows several types of channels:

* Direct channels contain a chat with a single user outside of a team
* Group channels contain a chat with a a group of users outside of a team
* Channels belonging to a team

You can configure for each type which channels should be backed up.


## Requirements

The script should work with Python 3.8 or later.
The [mattermost module](https://github.com/someone-somenet-org/mattermost-python-api) is needed for easier API access.

**Note** that we require a version with the additional endpoint `get_teams_for_user`. There is a currently open [pull request](https://github.com/someone-somenet-org/mattermost-python-api/pull/5) to add this endpoint to the package. Until the pull request is executed you may use  [its source branch](https://github.com/bjhend/mattermost-python-api/tree/endpoint/get_teams_for_user).

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

optional arguments:
  -h, --help            show this help message and exit
  --credentials CREDENTIALS
                        json file containing user name, password and server URL, default = credentials.json
  --channels CHANNELS   json file listing all channels to backup, default = channels.json
  -d DATA_DIR, --data-dir DATA_DIR
                        Dir to store downloaded data in, absolute or relative to current dir, default = data
  -o OUTPUT_ZIP, --output-zip OUTPUT_ZIP
                        zip file to write, default is 'matterbak_<user>.zip'
  --skip-direct         skip direct channels
  --skip-groups         skip group channels
  --skip-teams          skip team channels
```


## Running

We recommend to use `uv` or `poetry` to run the script. Otherwise install the dependencies defined in `pyproject.toml`, see section [Requirements](#Requirements) above.

The script creates up to four folders under the given *data-dir*: `teams`, `direct`, `groups`, and `users` with the respective channel or user data received from Mattermost.

Finally all data in the *data-dir* is stored in the *output-zip* file.


## Notes
There is also another more complete [Python implementation of the mattermost API](https://github.com/Vaelor/python-mattermost-driver) but it
needs more configuration.

The [official API docs](https://api.mattermost.com/) are also available.

## License

MIT
