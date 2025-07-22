"""Function to scan all the files in all user's directories to calculate quota usage.

 This script is designed to be run from the command line

  ``python xfc_scan.py --path /userdir``
"""

import datetime
import os
import click

@click.command()
@click.option('--path', type=click.Path(exists=True, file_okay=False, dir_okay=True, readable=True))
def scan_directory(path):
    """
    Scans all the files under a specific directoy and calculates:
        - Hard Quota - total size of all files.
        - Temporal Quota - sum of (file size * time present)

    params:
        path: The directory path specified by the user in the command line.
    """

    dir = os.path.join(path)
    user_file_list = os.walk(dir, followlinks=True)

    now = datetime.datetime.now()
    hard_quota = 0
    temporal_quota = 0

    for root, dirs, files in user_file_list:
        for file in files:
            try:
                filepath = os.path.join(root, file)
                stat = os.stat(filepath)
                size = stat.st_size
                created_time = datetime.datetime.fromtimestamp(stat.st_mtime) # use mtime as ctime returns diff values on different os
                days_present = (now - created_time).days + 1

                hard_quota += size
                temporal_quota += (size * days_present)
            except Exception as e:
                click.echo(f"Error processing {filepath}: {e}", err=True)
        
    
    click.echo(f"Hard Quota (bytes): {hard_quota}")
    click.echo(f"Temporal Quota (bytes): {temporal_quota}")

    

if __name__ == '__main__':
    scan_directory()