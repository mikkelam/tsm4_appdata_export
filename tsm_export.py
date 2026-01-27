import argparse
import enum
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Generator

import pandas as pd


class TSMDataType(enum.Enum):
    AUCTIONDB_NON_COMMODITY_HISTORICAL = "AUCTIONDB_NON_COMMODITY_HISTORICAL"
    AUCTIONDB_NON_COMMODITY_DATA = "AUCTIONDB_NON_COMMODITY_DATA"
    AUCTIONDB_NON_COMMODITY_SCAN_STAT = "AUCTIONDB_NON_COMMODITY_SCAN_STAT"
    AUCTIONDB_REGION_STAT = "AUCTIONDB_REGION_STAT"
    AUCTIONDB_REGION_HISTORICAL = "AUCTIONDB_REGION_HISTORICAL"
    AUCTIONDB_REGION_SALE = "AUCTIONDB_REGION_SALE"
    AUCTIONDB_COMMODITY_SCAN_STAT = "AUCTIONDB_COMMODITY_SCAN_STAT"
    AUCTIONDB_COMMODITY_DATA = "AUCTIONDB_COMMODITY_DATA"
    AUCTIONDB_COMMODITY_HISTORICAL = "AUCTIONDB_COMMODITY_HISTORICAL"

    def is_region_data(self) -> bool:
        return self in (
            TSMDataType.AUCTIONDB_REGION_STAT,
            TSMDataType.AUCTIONDB_REGION_HISTORICAL,
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
    # More defensive decoding: tolerate stray punctuation / unexpected tokens.
    raw_tokens = data_line.split(",")
    out: list[int] = []

    for tok in raw_tokens:
        tok = tok.strip().strip('"').upper()
        if not tok:
            out.append(0)
            continue

        # Fast path pure digits
        if tok.isdigit():
            out.append(int(tok))
            continue

        # Remove any non base32 characters (0-9 A-V) – TSM encoding uses base32 set.
        allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUV"
        cleaned = "".join(ch for ch in tok if ch in allowed)

        if not cleaned:
            out.append(0)
            continue

        try:
            if len(cleaned) > 6:
                val = int(cleaned[-6:], 32) + int(cleaned[:-6], 32) * (2**30)
            else:
                val = int(cleaned, 32)
        except ValueError:
            val = 0
        out.append(val)

    return tuple(out)


def parse_tsm_appdata(path: Path) -> Generator[TSMData, None, None]:
    """
    Parse the TSM AppData.lua file.

    The old implementation assumed each LoadData call was on a single line.
    In modern TSM (and in large datasets), each LoadData block can span multiple lines.
    This version:
      - Reads the entire file at once
      - Uses a DOTALL regex to capture multi-line data blocks
      - Extracts dataset metadata and decodes the compact base32-style numeric fields
    """
    text = path.read_text()

    # Example block prefix:
    # select(2, ...).LoadData("AUCTIONDB_NON_COMMODITY_DATA","Gehennas-Horde",[[return {downloadTime=1758316736,fields={"itemString","minBuyout","numAuctions","marketValueRecent"},data={{82211,1E2JF,2,1E2JF},{...}}}]])
    pattern = re.compile(
        r'select\(2,\s*\.\.\.\)\.LoadData\("([^"]+)"\s*,\s*"([^"]+)"\s*,\s*\[\[return {downloadTime=(\d+),fields=\{([^}]*)\},data=\{(.*?)\}\}\]\]',
        re.DOTALL,
    )

    for match in pattern.finditer(text):
        data_type = match.group(1)
        realm = match.group(2)
        download_time = int(match.group(3))
        header_str = match.group(4)
        data_str = match.group(5).strip()

        headers = [h.strip('"') for h in header_str.split(",") if h]

        # data_str looks like: {{row1},{row2},...}
        if data_str.startswith("{") and data_str.endswith("}"):
            inner = data_str[1:-1].strip()
        else:
            inner = data_str

        if not inner:
            rows = []
        else:
            # Split on '},{' boundaries between rows (rows themselves are simple lists).
            raw_rows = re.split(r"\},\{", inner)
            rows = []
            for r in raw_rows:
                r_clean = r.strip().lstrip("{").rstrip("}")
                if not r_clean:
                    continue
                rows.append(unpack_data(r_clean))

        yield TSMData(
            data_type=TSMDataType(data_type),
            realm=realm,
            download_time=download_time,
            headers=headers,
            data=rows,
        )


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
