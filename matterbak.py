#!/usr/bin/env python3
"""
matterbak does a backup for all channels of a user in a mattermost instance
"""
import argparse
import datetime
import json
import os
import zipfile

import mattermost

def main():
    """Main function, also entry point for the matterbak script"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--credentials", default="credentials.json",
                        help="json file containing user name, password and server URL")
    parser.add_argument("--backup-user",
                        help="user name to backup, default is the one from credentials")
    parser.add_argument("--output-zip",
                        help="zip file to write, default is 'matterbak_<user>.zip'")
    parser.add_argument("-x", "--exclude", default=[], nargs="*",
                        help="list of channel names to exclude")
    parser.add_argument("-i", "--include", nargs="*",
                        help="list of channel names to include")
    parser.add_argument("-a", "--all", action="store_true", default=False,
                        help="include also public channels")
    options = parser.parse_args()
    with open(options.credentials, encoding="utf8") as cred_file:
        creds = json.load(cred_file)
    if options.backup_user is None:
        options.backup_user = creds["user"]
    if options.output_zip is None:
        options.output_zip = "matterbak_%s.zip" % options.backup_user
    matter = mattermost.MMApi(creds["url"])
    if "token" in creds:
        matter.login(bearer=creds["token"])
    else:
        matter.login(creds["user"], creds["password"])
    for cat in ("teams", "channels", "users"):
        os.makedirs(cat, exist_ok=True)
    user = matter.get_user_by_username(options.backup_user)
    with open(os.path.join("users", user["username"] + ".json"), "w", encoding="utf8") as desc:
        json.dump(user, desc)
    channels = []
    user_data = {}
    for team in matter.get_teams():
        try:
            for member in matter.get_users_by_ids_list([m["user_id"] for m in matter.get_team_members(team["id"])]):
                user_data[member["id"]] = member
            if user["id"] in user_data:
                with open(os.path.join("teams", team["name"] + ".json"), "w", encoding="utf8") as desc:
                    json.dump(team, desc)
                for chnl in matter.get_channels_for_user(user["id"], team["id"]):
                    if options.all or chnl["type"] != "O":
                        if options.include:
                            if chnl["display_name"] in options.include or chnl["name"] in options.include:
                                channels.append(chnl)
                        elif chnl["display_name"] not in options.exclude and chnl["name"] not in options.exclude:
                            channels.append(chnl)
        except mattermost.ApiException as e:
            print(team, e)
    print(channels)
    for chnl in channels:
        name = chnl["name"]
        for i, data in user_data.items():
            name = name.replace(i, data["username"])
        prefix = os.path.join("channels", name)
        os.makedirs(prefix, exist_ok=True)
        with open(prefix + ".json", "w", encoding="utf8") as desc:
            json.dump(chnl, desc)
        for post in matter.get_posts_for_channel(chnl["id"]):
            date = datetime.datetime.fromtimestamp(post["create_at"] / 1000).strftime("%Y%m%d-%H%M%S%f")
            post_json = os.path.join(prefix, date + "." + post["id"] + ".json")
            if not os.path.exists(post_json):
                with open(post_json, "w", encoding="utf8") as desc:
                    json.dump(post, desc)
            if post["user_id"] in user_data:
                user_json = os.path.join("users", user_data[post["user_id"]]["username"] + ".json")
                if not os.path.exists(user_json):
                    with open(user_json, "w", encoding="utf8") as desc:
                        json.dump(user_data[post["user_id"]], desc)
            for file_desc in post["metadata"].get("files", []):
                ext = file_desc["extension"]
                file_dump = os.path.join(prefix, file_desc["id"] + "." + ext)
                if not os.path.exists(file_dump):
                    with open(file_dump, "wb") as dump:
                        dump.write(matter.get_file(file_desc["id"]).content)
    with zipfile.ZipFile(options.output_zip, "w") as zipf:
        for d in ("teams", "users"):
            for f in os.listdir(d):
                zipf.write(os.path.join(d, f))
        for root, _, files in os.walk("channels"):
            for f in files:
                zipf.write(os.path.join(root, f))


if __name__ == "__main__":
    main()
