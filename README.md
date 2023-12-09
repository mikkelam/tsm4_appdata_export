# tsm4_appdata_export
Small python script to read the AppData.lua from TSM4's apphelper.

Untested on Windows and Linux


Region and realm data files will be exported like this:
```
classic_era_SoD-EU.csv
classic_era_Living Flame-Alliance.csv
...
```

with contents like this (region data here):
```
itemString,regionHistorical,regionMarketValue,regionSale,regionSoldPerDay,regionSalePercent
101,119900,390706,330585,0,12
102,3000000,24220047,0,0,0
```

# Installation
``` bash
git clone https://github.com/mikkelam/tsm4_appdata_export.git
cd tsm4_appdata_export
pip3 install -r requirements.txt
```

# Usage
``` bash
python3 tsm_export.py -h
usage: tsm_export.py [-h] [-f FORMAT] -r APP_PATH [-o OUTPUT]

Export TSM4 AppData.lua to data tables

options:
  -h, --help            show this help message and exit
  -f FORMAT, --format FORMAT
                        output file format. Options: ('json', 'csv', 'pickle', 'hdf5', 'xlsx')
  -r APP_PATH, --app_helper_path APP_PATH
                        Path to AppData.lua
  -o OUTPUT, --output_dir OUTPUT
                        Path to output directory
```

## Example export

To export data from classic_era to csv
``` bash
python3 tsm_export.py -r "/Applications/World of Warcraft/_classic_era_/Interface/AddOns/TradeSkillMaster_AppHelper/AppData.lua" -o data/ -f csv
```

If run correctly, it should output something like this:
```
Found 4 realms and 3 regions
Saved data/classic_era_Skull Rock-Horde.csv with 2460 rows.
Saved data/classic_era_Skull Rock-Alliance.csv with 2695 rows.
Saved data/classic_era_Defias Pillager-Alliance.csv with 3890 rows.
Saved data/classic_era_Living Flame-Alliance.csv with 2155 rows.
Saved data/classic_era_HC-US.csv with 6351 rows.
Saved data/classic_era_HC-EU.csv with 6219 rows.
Saved data/classic_era_SoD-EU.csv with 3347 rows.
```