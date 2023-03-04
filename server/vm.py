"""Main function contains functionality for the API and the UI, as well as the MongoDB queries and data processing"""

import os
import datetime
import time
from dataclasses import dataclass
import pandas as pd
import requests
from flask import jsonify
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

API_KEY = os.getenv("API_KEY")
API_HOST = os.getenv("API_HOST")
MDB_URL = os.getenv("MDB_URL")
cluster = MongoClient(MDB_URL)
db = cluster["milData"]
collection = db["historicalData"]


def current_time():
    """Returns time in UTC"""

    return datetime.datetime.now(datetime.timezone.utc).time()


def day():
    """Returns date in UTC"""

    return datetime.date.today().strftime("%Y-%m-%d")


def day_obj():
    """Returns date in UTC as a datetime object"""

    return datetime.date.today()


def delay_time():
    """Sets the delay time based on the current time of day"""

    if datetime.time(4, 0) <= current_time() <= datetime.time(19, 0):
        return 350
    elif datetime.time(19, 0) < current_time() <= datetime.time(23, 59):
        return 750
    elif datetime.time(0, 1) < current_time() <= datetime.time(3, 59):
        return 450
    else:
        return 550


def get_data():
    """Gets data from the API and returns it as a JSON object"""

    url = "https://adsbexchange-com1.p.rapidapi.com/v2/mil/"

    headers = {
        "X-RapidAPI-Key": API_KEY,
        "X-RapidAPI-Host": API_HOST
    }
    response = requests.request(
        "GET", url, headers=headers, timeout=3)  # type: ignore
    data = response.json()
    if len(data) == 0:
        print(f"No data collected {current_time}")
        return get_data()
    else:
        print(f"Data collected {current_time}")
    return data


@dataclass
class Main:
    """Class for main, used to return data to the UI"""

    main_data = {}
    post_data = {}
    date: str = day()
    ac_type = pd.Series(['EUFI', 'F16', 'V22', 'F18S', 'A10',
                        'F35LTNG', 'F35', 'C2', 'E2', 'S61',
                         'B742\nBoeing E-4B', 'H64', 'F15',
                         'AV8B', 'RC135'])
    df = {'hex': [], 'flight': [], 't': [], 'r': [], 'squawk': []}

    @classmethod
    def pre_proccess(cls):
        """Removes duplicates and extraneous data"""

        for item in cls.main_data['ac']:
            hex_val = item['hex']
            if hex_val not in cls.df['hex']:
                cls.df['hex'].append(hex_val)
                cls.df['flight'].append(item.get('flight', 'None').strip())
                cls.df['t'].append(item.get('t', 'None'))
                cls.df['r'].append(item.get('r', 'None'))
                cls.df['squawk'].append(item.get('squawk', 'None'))
        df_data = pd.DataFrame(cls.df)
        df_data.drop(df_data[df_data['r'] == 'TWR'].index, inplace=True)
        df_data.drop(df_data[df_data['t'] == 'GND'].index, inplace=True)
        df_data.drop(df_data[df_data['flight'] =='TEST1234'].index, inplace=True) # fmt: off
        return df_data.to_dict(orient='records')

    @classmethod
    def auto_req(cls):
        """Automatically requests data from the API and writes it to a JSON file
        at a specified interval as defined by the DELAY variable"""

        while True:
            cls.main_data.update(get_data())
            cls.pre_proccess()
            time.sleep(delay_time())

    @classmethod
    def mdb_insert(cls):
        """Inserts data into MongoDB"""

        doc = {"_id": f"{day}", "data": cls.pre_proccess(),
               "stats": cls.ac_count(), "inter": cls.inter_ac()}
        collection.insert_one(doc)
        print(f"Data inserted into MongoDB {current_time} ")

    @classmethod
    def ac_count(cls):
        """Returns the total number of aircraft in the data"""

        ac_data = pd.DataFrame(cls.pre_proccess())
        count = pd.value_counts(ac_data['t']).to_dict()
        new_list = []
        for key, value in count.items():
            new_dict = {"type": key, "value": value}
            new_list.append(new_dict)
        return new_list

    @classmethod
    def inter_ac(cls):
        """Returns objects that contain an aircraft type specified in the ac_type"""

        interesting_ac = pd.DataFrame(cls.pre_proccess())
        inter_data = interesting_ac[interesting_ac['t'].isin(
            cls.ac_type)].to_dict(orient='records')
        if inter_data == []:
            return jsonify({"message": "No interesting aircraft found"})
        else:
            return inter_data


def rollover():
    """Checks the time every second and runs the mdb_insert function at 11:59:55pm"""

    while True:
        if datetime.datetime.now().strftime('%H:%M:%S') == '23:59:55':
            Main.mdb_insert()
        time.sleep(1)

def get_weekly_data(day_amount: int):
    """Returns a list of dates"""
    data = []

    for i in range(day_amount):
        date = day_obj() - datetime.timedelta(days=i)
        data.append(date.strftime("%Y-%m-%d"))
    return data