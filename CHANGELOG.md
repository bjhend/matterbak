# Changelog

## Next

* Fix: Detection of already downloaded posts fails on some systems. Thanks Sirko
       for discovering and fixing this.
* Fix: Archived channels are entirely ignored by matterbak. Thanks Sirko for
       discovering this and finding a fix.

## 0.5.1

* Fix: `matterexport` fails when searching for channel by its ID
* Fix: Crash of `matterexport` if user data are not found. This may happen if a
       user has left Mattermost.

## 0.5.0

* Increase minimum Python version to 3.10 to enable `matterexport`
* Add `matterexport` script to export stored data

## 0.4.0

* Avoid termination during file saving to avoid corrupted files
* Print '+' as progress symbol when a post is actually saved
* Improve determination of thread relations resulting in a new format
  for thread files
  - **Attention:** To update the thread files run once with option
  `--update-old-posts`
* Add option `--version`
* Don't export any package functions or classes as it is currently only
  supposed as command line tool
* Append internal team name to paths instead of eventually the display_name to
  avoid potential problems with unsuitable characters
  - **Attention:** To update the paths delete the teams folder and repeat
    matterbak while you may skip anything except teams
* Improve code quality by automatic lint check
* Integrate our extensions to mattermost package to avoid problems with using
  a fork on Github. Particularly PyPI does not allow GitHub repos as dependency.
* Publish on PyPI for easier installation

## 0.3.1

**Note**: This should have been a minor instead of a patch release.

* More messages
* Catch more errors
* Put ID as prefix to all saved files to ensure they are unique and
  make cross refs easy
* Save channel member data
* Fix: crash if too many user data are requested at once
* Catch more errors
* Save team icons
* Save user images
* Add more command line options
* Save custom emojis
* Save thread relations of posts
* Add option to update all old posts (to catch edits of old posts)
* Add rate limits for Mattermost API calls to prevent server overload
* Format output messages to make copying to channels config easier

## 0.3.0

* Only download new posts

## 0.2.0

* Add `pyproject.toml` to enable `uv` or `poetry` usage
* Introduce channel config
* Backup also direct and group channels if configured
* Backup user data
* Add options to skip direct, group, or team channels
* Drop support to use a different backup user
* Some bug fixes

## 0.1.0

**Note**: Not assigned

## 0.0.1

Initial fork from
[github.com/behrisch/matterbak](https://github.com/behrisch/matterbak)
