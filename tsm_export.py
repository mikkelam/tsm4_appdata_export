import argparse
from collections import defaultdict
from dataclasses import dataclass
import enum
from pathlib import Path
import re
from typing import Generator
import pandas as pd


class TSMDataType(enum.Enum):
    AUCTIONDB_REALM_SCAN_STAT = "AUCTIONDB_REALM_SCAN_STAT"
    AUCTIONDB_REALM_DATA = "AUCTIONDB_REALM_DATA"
    AUCTIONDB_REALM_HISTORICAL = "AUCTIONDB_REALM_HISTORICAL"
    AUCTIONDB_REGION_HISTORICAL = "AUCTIONDB_REGION_HISTORICAL"
    AUCTIONDB_REGION_STAT = "AUCTIONDB_REGION_STAT"
    AUCTIONDB_REGION_SALE = "AUCTIONDB_REGION_SALE"

    def is_region_data(self) -> bool:
        return self in (
            TSMDataType.AUCTIONDB_REGION_HISTORICAL,
            TSMDataType.AUCTIONDB_REGION_STAT,
            TSMDataType.AUCTIONDB_REGION_SALE,
        )


@dataclass
class TSMData:
    data_type: TSMDataType
    realm: str  # or region name
    download_time: int
    headers: list[str]
    data: list[tuple[int, ...]]


def unpack_data(data_line: str) -> tuple[int, ...]:
    # Split the data string into an array and process each value
    tbl_data = data_line.split(",")

    for i in range(len(tbl_data)):
        val = tbl_data[i]
        if val.isdigit():
            # Handle integer values
            val = int(val)
        # string encoded numbers
        elif len(val) > 6:
            # Handle long values
            val = int(val[-6:], 32) + int(val[:-6], 32) * (2**30)
        else:
            val = int(val, 32)
        tbl_data[i] = val

    return tbl_data


def parse_tsm_appdata(path: Path) -> Generator[TSMData, None, None]:
    pattern = r'LoadData\("([^"]+)",\s*"([^"]+)",.*\{downloadTime=(\d+),fields=\{([^}]+)\},data=\{(.+)}\}\]\]'
    with open(path, "r") as file:
        for idx, line in enumerate(file):
            match = re.search(pattern, line)
            if match:
                data_type = match.group(1)
                realm = match.group(2)
                download_time = int(match.group(3))
                header_str = match.group(4)
                data_str = match.group(5)

                # split the h
                headers = header_str.replace('"', "").split(",")
                data_groups = data_str[1:-1].split("},{")

                data = [unpack_data(group) for group in data_groups]
                yield TSMData(
                    data_type=TSMDataType(data_type),
                    realm=realm,
                    download_time=download_time,
                    headers=headers,
                    data=data,
                )

            else:
                if "APP_INFO" in line:
                    # ignore the app info lines
                    pass
                else:
                    print(f"No match for line {idx}: {line:.50}")


def join_data(data: list[TSMData], join_col: str = "itemString") -> pd.DataFrame:
    first = data.pop(0)
    df = pd.DataFrame(first.data, columns=first.headers)

    for tsm_data in data:
        df = df.merge(
            pd.DataFrame(tsm_data.data, columns=tsm_data.headers),
            on=join_col,
            how="inner",
        )
    return df


def save_data(df: pd.DataFrame, path: Path, format: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    if format == "csv":
        df.to_csv(path, index=False)
    elif format in ("json", "yml", "yaml"):
        df.to_json(path, index=False)
    elif format in ("hdf", "hdf5"):
        df.to_hdf(path, "dataframe")
    elif format in ("pickle", "pkl"):
        df.to_pickle(path)
    elif format in ("excel", "xls", "xlsx"):
        df.to_excel(path, index=False)

    print(f"Saved {path} with {len(df)} rows.")


def main():
    tsm_log = None

    parser = argparse.ArgumentParser(
        description="Export TSM4 AppData.lua to data tables"
    )

    format_options = ("json", "csv", "pickle", "hdf5", "xlsx")
    parser.add_argument(
        "-f",
        "--format",
        metavar="FORMAT",
        type=str,
        default="csv",
        help=f"output file format. Options: {format_options}",
        dest="format",
        choices=format_options,
    )
    parser.add_argument(
        "-r",
        "--app_helper_path",
        metavar="APP_PATH",
        type=str,
        required=True,
        help="Path to AppData.lua",
        dest="app_helper_path",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        metavar="OUTPUT",
        type=str,
        default=".",
        help="Path to output directory",
        dest="output_dir",
    )

    args = parser.parse_args()

    app_helper_path = Path(args.app_helper_path)

    wow_version = app_helper_path.parent.parent.parent.parent.name.strip("_")
    output_dir = Path(args.output_dir)

    realm_data = defaultdict(list)
    historical_data = defaultdict(list)
    for tsm_data in parse_tsm_appdata(app_helper_path):
        if tsm_data.data_type.is_region_data():
            historical_data[tsm_data.realm].append(tsm_data)
        else:
            # append to a list
            realm_data[tsm_data.realm].append(tsm_data)

    print(f"Found {len(realm_data)} realms and {len(historical_data)} regions")

    # loop over both dicts and join the data
    for data in [realm_data, historical_data]:
        for realm, tsm_data in data.items():
            df = join_data(tsm_data)
            save_data(df, output_dir / f"{wow_version}_{realm}.csv", args.format)

    # print(f"Found {len(realm_data)} realms")
    # print(f"Found {len(historical_data)} regions")


if __name__ == "__main__":
    main()
