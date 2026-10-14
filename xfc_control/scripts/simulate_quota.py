#! /usr/bin/env python
"""
Simulate the XFC temporal quota.
The XFC now calculates the temporal quota from a number of scans of the user's
directories, that take place at subsequent timestamps.  The scans only return the total
size of the directory and the timestamp.
The used temporal quota should be an integral of the amount of space used over time, but
this has to also be allowed to be negative, and to decay over time back to 0.
"""

from datetime import datetime, timedelta


class Scan:
    """Quick scan class to hold the scan_time and the size_bytes"""

    def __init__(self, size_bytes: int, scan_time: datetime):
        self.size_bytes = size_bytes
        self.scan_time = scan_time


def create_scans() -> list[Scan]:
    """Create a list of fake scans at daily intervals"""
    sizes = [
        7800,
        7800,
        7800,
        7800,
        6800,
        100,
        100,
        100,
        200,
        300,
        400,
        400,
        10000,
        10000,
        400,
        0,
        400,
    ]
    timenow = datetime.now()
    scans = []

    for i in range(0, len(sizes)):
        # scan every day
        scan = Scan(sizes[i], timenow)
        timenow += timedelta(days=1)
        scans.append(scan)
    return scans


def calculate_temporal_usage(scans: list[Scan]):
    """Calculate the temporal usage.
    This is as simple as the length of time between scans multiplied by the scan size.
    The complication comes when the scan size is less than the previous scan size.
    Then an adjustment phase is used.  See comments below
    """
    temporal_size = scans[0].size_bytes
    n_secs_day = 24 * 60 * 60
    for i in range(1, len(scans)):
        # Check if an adjustment is needed
        if scans[i].size_bytes < scans[i - 1].size_bytes:
            # This is the adjustment phase.  The adjustment algorithm is as follows:
            # 1. Scan back in the array to find when the first instance of when the
            #    scan size was lower than the current size.
            # 2. Delete from the temporal size the product of:
            #       the difference in time between now and when the scan size was lower
            #     * the difference in scan size for those times

            # get the index when the scan size was lower than the current scan size
            d = i - 1  # previous index
            while scans[d].size_bytes > scans[i].size_bytes and d > 0:
                d -= 1
                # don't fall into a local minima
                while scans[d - 1].size_bytes >= scans[d].size_bytes and d > 0:
                    d -= 1
            # get the time difference
            td = (scans[i].scan_time - scans[d].scan_time).total_seconds() / n_secs_day
            # get the size difference
            sd = scans[i].size_bytes - scans[d].size_bytes
            print("D:", d, i, td, sd, temporal_size, td * sd)
            # delete from temporal size
            temporal_size += sd * td
            # clamp the size to 0
            if temporal_size < 0:
                temporal_size = 0
        # Now add the temporal_size for this scan
        td = (scans[i].scan_time - scans[i - 1].scan_time).total_seconds() / n_secs_day
        temporal_size += scans[i].size_bytes * td
    return temporal_size


def calculate_temporal_usage_2(scans: list[Scan]):
    """
    Calculate the temporal usage.
    This is as simple as the length of time between scans multiplied by the scan size.
    The complication comes when the scan size is less than the previous scan size.
    To counteract this the algorithm is:
        1. The maximum size is the size of the latest scan = max_size
        2. For each scan, the contribution to the temporal usage is the minimum of the
           scan and the maximum size * time between scans:
           C = min(scan_size, max_size) * time_delta

    This can be thought of via the following scenario:
        1. The user adds data to the volume, it keeps increasing.  The temporal usage
           goes up in line with this.
        2. The user removes data from the volume. It drops to X bytes.
        3. The temporal usage still needs to reflect that this amount of data has been
           present since the scan size was above or equal to X.
        4. Hence taking the min between the latest scan size and the sizes for
           each of the scans.
    """
    max_size = scans[-1].size_bytes  # maximum size of scan
    # start with initial scan size, but it also has to obey the max size requirement
    temporal_size = min(scans[0].size_bytes, max_size)
    n_secs_day = 24 * 60 * 60  # number of seconds per day

    for i in range(1, len(scans)):
        c_scan_size = min(scans[i].size_bytes, max_size)
        td = (scans[i].scan_time - scans[i - 1].scan_time).total_seconds()
        temporal_size += c_scan_size * td / n_secs_day
    return temporal_size


def calculate_temporal_usage_3(scans: list[Scan]):
    """
    Calculate the temporal usage.
    This is as simple as the length of time between scans multiplied by the scan size.
    The complication comes when the scan size is less than the previous scan size.
    To counteract this the algorithm is:
        1. Calculate the temporal usage backwards, i.e. start with the latest scan
        1. The maximum size is the size of the current scan = max_size
        2. For each scan, the contribution to the temporal usage is the minimum of the
           scan and the maximum size * time between scans:
           C = min(scan_size, max_size) * time_delta
        3. Update the maximum size at each iteration.  This

    This can be thought of via the following scenario:
        1. The user adds data to the volume, it keeps increasing.  The temporal usage
           goes up in line with this.
        2. The user removes data from the volume. It drops to X bytes.
        3. The temporal usage still needs to reflect that this amount of data has been
           present since the scan size was above or equal to X.
        4. Hence taking the min between the latest scan size and the sizes for
           each of the scans.
        5. The usage could drop to Y bytes where Y < X, before the user adds more data
           to take the latest scan to X bytes.
        6. This is why the scan is performed backwards, and the max_size is constantly
           updated.
    """
    max_size = scans[-1].size_bytes  # maximum size of scan
    n_secs_day = 24 * 60 * 60  # number of seconds per day
    temporal_size = scans[-1].size_bytes  # start with latest scan size
    n_scans = len(scans)

    # loop backwards
    for i in range(n_scans - 1, 0, -1):
        # get the minimum scan size
        c_scan_size = min(scans[i - 1].size_bytes, max_size)
        # get the time delta
        td = (scans[i].scan_time - scans[i - 1].scan_time).total_seconds()
        temporal_size += c_scan_size * td / n_secs_day
        # update max size
        max_size = min(max_size, scans[i - 1].size_bytes)
    return temporal_size


def main():
    scans = create_scans()
    for i in range(0, len(scans)):
        c_scans = scans[0 : i + 1]
        # This is the correct calculation !!!
        print(calculate_temporal_usage_3(c_scans), c_scans[-1].size_bytes)


if __name__ == "__main__":
    main()
