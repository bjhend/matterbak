#!/usr/bin/env python3
"""
mattermerge merges multiple backups done with matterbak into a jsonl file
usable by the mattermost bulk import
https://docs.mattermost.com/onboard/bulk-loading-data.html#data-format
"""
import argparse
import json
import zipfile

def print_json(typ, content, jsonl):
    json.dump({ "type": typ, typ: content}, jsonl)
    print(file=jsonl)


def main():
    """Main function, also entry point for the matterbak script"""
    parser = argparse.ArgumentParser()
    parser.add_argument("zips", nargs="+",
                        help="input zip files")
    parser.add_argument("-o", "--output", default="matter.jsonl",
                        help="jsonl file to write, default is 'matter.jsonl'")
    parser.add_argument("-a", "--attachments", action="store_true", default=False,
                        help="include also attachments")
    options = parser.parse_args()
    zips = [zipfile.ZipFile(z) for z in options.zips]
    with open(options.output, "w", encoding="utf8") as jsonl:
        print_json("version", 1, jsonl)
        teams = {}
        for z in zips:
            for n in z.namelist():
                if n.startswith("teams/"):
                    team = json.load(z.open(n))
                    if team["id"] in teams:
                        continue
                    teams[team["id"]] = team["name"]
                    keys = ("name", "display_name", "type", "description", "allow_open_invite")
                    print_json("team", {key: team[key] for key in keys}, jsonl)
        users = {}
        channels = {}
        direct = set()
        for z in zips:
            for n in z.namelist():
                if n.startswith("channels/") and n.count("/") == 1:
                    channel = json.load(z.open(n))
                    cdir = n[:-5] + "/"
                    if cdir not in channels:
                        channel["team"] = teams.get(channel["team_id"], "")
                        channels[cdir] = (z, channel["team"], channel["name"])
                        if channel["type"] in "OP":
                            keys = ("team", "name", "display_name", "type", "header", "purpose")
                            print_json("channel", {key: channel[key] for key in keys}, jsonl)
                        else:
                            direct.add(cdir)
                if n.startswith("users/"):
                    user = json.load(z.open(n))
                    if user["email"] or user["id"] not in users:
                        users[user["id"]] = user
        for user in users.values():
            keys = ("username", "email", "nickname", "first_name", "last_name",
                    "position", "roles", "locale")
            udump = {key: user[key] for key in keys}
            if "notify_props" in user:
                udump["notify_props"] = user["notify_props"]
            print_json("user", udump, jsonl)
        for cdir, (z, team, cname) in channels.items():
            if cdir not in direct:
                for n in z.namelist():
                    if n.startswith(cdir + "20") and n.endswith(".json"):
                        post = json.load(z.open(n))
                        post.update({"team": team, "channel": cname, "user": users[post["user_id"]]["username"]})
                        keys = ("team", "channel", "user", "message", "props", "create_at")
                        print_json("post", {key: post[key] for key in keys}, jsonl)


if __name__ == "__main__":
    main()
