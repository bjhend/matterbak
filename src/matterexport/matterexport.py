


import argparse
import pathlib as pl
import importlib.metadata
from . import markdown


default_data_dir = pl.Path('data')


def _parse_command_line():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--type", default='markdown',
                        choices=['markdown'],
                        help="Type of export, default = %(default)s")
    parser.add_argument("-d", "--data-dir", type=pl.Path, default=default_data_dir,
                        help="Dir with downloaded data, absolute or relative to current dir, default = %(default)s")
    parser.add_argument("-o", "--output",
                        help="Export destination (interpretation depends on --type)")
    parser.add_argument("-c", "--channel",
                        help="Channel to export, either channel ID, internal name, or directory")
    parser.add_argument("--threads", action="store_true", default=False,
                        help="Sort posts by threads if applicable")
    parser.add_argument('--version', action='version', version=importlib.metadata.version('matterbak'))
    return parser.parse_args()


def main():
    args = _parse_command_line()
    match args.type:
        case 'markdown':
            exporter_type = markdown.Markdown_Exporter
        case _:
            print(f"Type {args.type} is not valid")
            exit(1)

    with exporter_type(args.data_dir, args.output) as exporter:
        if args.channel:
            exporter.channel(args.channel, args.threads)

