#!/usr/bin/python

import locale
import netrc
import os
import re
import requests
import ConfigParser
from bs4 import BeautifulSoup
from datetime import datetime
from requests_ntlm import HttpNtlmAuth
import boto3
import botocore
import json
from boto3.dynamodb.conditions import Key, Attr


class ConfigInput:
    def __init__(self):
        pass

    @property
    def netrc(self):
        return 'netrc'

    @property
    def dynamodb(self):
        return 'dynamo_db'


class DataInput:
    def __init__(self):
        pass

    @property
    def json(self):
        return 'json'

    @property
    def https(self):
        return 'HTTPS'


class SiouxParser:
    _RAW_EVENTS = None
    _RAW_BDAYS = None

    # Filter keys for events/bdays
    _ONE_DAY = 'one_day'
    _MUL_DAY = 'multiple_days'
    _TODAY = 'today'
    _FUTURE = 'future'
    _PAST = 'past'
    _AGE = 'age'

    # Config file
    _CONFIG_FILE = 'config.ini'

    def __init__(self, config_input, data_input, path_config_file=None):
        """
        Parser for Sioux BE intranet.\n

        :param path_config_file: Path to the configuration file. (default: current directory)\n
        """

        if config_input == ConfigInput.netrc:
            self._get_config = self._get_config_netrc

            if path_config_file is not None:
                path = path_config_file
            else:
                path = os.getcwd()

            self._conf = ConfigParser.ConfigParser()
            config_file = os.path.join(path, self._CONFIG_FILE)

            if os.path.isfile(config_file):
                self._conf.read(config_file)
            else:
                raise RuntimeError("Could not locate config file '%s'." % config_file)
            self._load_configuration()
        elif config_input == ConfigInput.dynamodb:
            self._get_config = self._get_config_dynamo_db

            self._dynamodb = boto3.resource('dynamodb', region_name='us-west-2', endpoint_url="http://localhost:8000")

            self._tables = {
                'URLS': self._dynamodb.Table('SIOUX_URLS'),
                'EVENTS': self._dynamodb.Table('SIOUX_EVENTS'),
                'PARSE_EV': self._dynamodb.Table('SIOUX_PARSE_EV'),
                'PARSE_BDAY': self._dynamodb.Table('SIOUX_PARSE_BDAY'),
                'P_D': self._dynamodb.Table('SIOUX_P_D')
            }
            self._load_configuration()
        else:
            raise RuntimeError('Wrong config_input argument! Use property of ConfigInput class')

        if data_input == DataInput.json:
            self._get_events = self._get_events_json
            self._get_recent_birthdays = self._get_recent_birthdays_json
            return
        elif data_input == DataInput.https:
            self._get_events = self._get_events_https
            self._get_recent_birthdays = self._get_recent_birthdays_https
            locale.setlocale(locale.LC_TIME, "nl_BE")
            self._session = None
            self.authenticate()
        else:
            raise RuntimeError('Wrong data_input argument! Use property of DataInput class')

    def _get_config_netrc(self, key, value):
        """
        Get configuration value from config file.\n

        :param key:   Key found in configuration value. (string)\n
        :param value: Value associated with said key. (string)\n
        :return: Configuration value. (string)\n
        """
        return self._conf.get(key, value)

    def _get_config_dynamo_db(self, key, value):
        try:
            response = self._tables[key].query(KeyConditionExpression=Key('key').eq(value))
        except botocore.exceptions.ClientError as e:
            print(e.response['Error']['Message'])
        else:
            if len(response['Items']) != 1:
                print 'Unexpected response: key:%s value:%s %s' % (key, value, response)
                exit(1)
            return response['Items'][0]['value']

    def _load_configuration(self):

        self._iis_domain = self._get_config('URLS', 'IIS_DOMAIN')
        self._base_url = self._get_config('URLS', 'BASE')
        self._baseIntraUrl = self._get_config('URLS', 'BASE_INTRA')
        self._eventsOverviewUrl = self._baseIntraUrl + self._get_config('URLS', 'EVENTS_OVERVIEW_EXT')
        self._birtdayUrl = self._baseIntraUrl + self._get_config('URLS', 'BDAY_EXT')

        # Event categories:
        self._evCatSocialPartner = self._get_config('EVENTS', 'SOCIAL_PARTNER')
        self._evCatSocialColleague = self._get_config('EVENTS', 'SOCIAL_COLLEAGUE')
        self._evCatPowwow = self._get_config('EVENTS', 'POWWOW')
        self._evCatTraining = self._get_config('EVENTS', 'TRAINING')
        self._evCatExpGroup = self._get_config('EVENTS', 'EXP_GROUP')
        self._evPresentation = self._get_config('EVENTS', 'PRESENTATION')

        # Parse events:
        self._ev_parse_element = self._get_config('PARSE_EV', 'ELEMENT_EV')
        self._ev_parse_arg = self._get_config('PARSE_EV', 'ARG_EV')

        self._ev_value_date = self._get_config('PARSE_EV', 'VALUE_DATE_EV')
        self._ev_value_title = self._get_config('PARSE_EV', 'VALUE_TITLE_EV')
        self._ev_value_location = self._get_config('PARSE_EV', 'VALUE_LOCATION_EV')
        self._ev_value_category = self._get_config('PARSE_EV', 'VALUE_CATEGORY_EV')

        # Parse bday:
        self._bday_today = self._get_config('PARSE_BDAY', 'TITLE_TODAY_BDAY')
        self._bday_future = self._get_config('PARSE_BDAY', 'TITLE_FUTURE_BDAY')
        self._bday_past = self._get_config('PARSE_BDAY', 'TITLE_PAST_BDAY')

        self._bday_parse_element = self._get_config('PARSE_BDAY', 'ELEMENT_BDAY')
        self._bday_parse_arg = self._get_config('PARSE_BDAY', 'ARG_BDAY')
        self._bday_parse_overall = self._get_config('PARSE_BDAY', 'VALUE_OVERALL_BDAY')
        self._bday_parse_separate = self._get_config('PARSE_BDAY', 'VALUE_SEPARATE_BDAY')

        self._p_d_tab = self._get_config('P_D', 'TAB'),
        self._p_d_tab_arg = self._get_config('P_D', 'TAB_ARG')
        self._p_d_tab_value = self._get_config('P_D', 'TAB_VALUE')
        self._p_d_rec_element = self._get_config('P_D', 'REC_ELEMENT')
        self._p_d_rec_arg = self._get_config('P_D', 'REC_ARG')
        self._p_d_rec_value = self._get_config('P_D', 'REC_VALUE')
        self._p_d_date_element = self._get_config('P_D', 'DATE_ELEMENT')
        self._p_d_date_arg = self._get_config('P_D', 'DATE_ARG')
        self._p_d_date_value = self._get_config('P_D', 'DATE_VALUE')

        self._bday_collegue = self._get_config('PARSE_BDAY', 'ROLE_COLLEGUE_BDAY')

    @property
    def _curr_date(self):
        return datetime.now().date()

    @property
    def _curr_year(self):
        return datetime.now().date().year

    @property
    def _curr_month(self):
        return datetime.now().date().month

    @property
    def _curr_day(self):
        return datetime.now().date().day

    @staticmethod
    def _prettify_string(string):
        """
        Remove tabs, newlines and leading/trailing spaces.\n

        :param string: String containing clutter.\n
        :return: Prettified string. (string)\n
        """
        return string.strip().replace('\n', '').replace('\t', '')

    @staticmethod
    def _parse_event_date(string):
        """
        Parse a string to find all event dates.\n

        :param string: Human readable date.\n
        :return: Dates (List of datetime.date)\n
        """
        m = re.findall("\d\d +[a-z]+ '\d\d", string)
        if m:
            return [datetime.strptime(dateString, "%d %b '%y").date() for dateString in m]
        else:
            return None

    def _fetch_data(self, url):
        """
        Get html data from a certain URL.\n

        :param url: url to get html from.\n
        :return: html stream (string)\n
        """
        if self._session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting birthdays!')

        req = self._session.get(url)
        if not req.ok:
            raise RuntimeError("Bad response!")
        return req.text

    def _get_events_json(self):
        with open('sioux_events.json', 'r') as fp:
            json_dump = json.load(fp)

            i = 0
            for dates in json_dump['Date']:
                j = 0
                for date in dates:
                    json_dump['Date'][i][j] = datetime.strptime(date, "%Y-%m-%d").date()
                    j = j + 1
                i = i + 1

            self._RAW_EVENTS = json_dump

    def _get_events_https(self):
        """
        Get all events from the events page and store it in member _RAW_EVENTS.\n

        :return: None\n
        """
        parseable_text = self._fetch_data(self._eventsOverviewUrl)

        soup = BeautifulSoup(parseable_text, "html.parser")

        dict_events = {"Date": [], "Title": [], "Loc": [], "Cat": [], "Url": []}

        dates = [self._parse_event_date(datee.text) for datee in soup.find_all(self._ev_parse_element, {self._ev_parse_arg: self._ev_value_date})]
        titles = soup.find_all(self._ev_parse_element, {self._ev_parse_arg: self._ev_value_title})
        location = soup.find_all(self._ev_parse_element, {self._ev_parse_arg: self._ev_value_location})
        category = [self._prettify_string(catt.text) for catt in soup.find_all(self._ev_parse_element, {self._ev_parse_arg: self._ev_value_category})]

        for dateEv, titleEv, locEv, catEv in zip(dates, titles, location, category):
            dict_events['Date'].append(dateEv)
            dict_events['Title'].append(self._prettify_string(titleEv.text))
            dict_events['Loc'].append(self._prettify_string(locEv.text))
            dict_events['Cat'].append(catEv)
            dict_events['Url'].append(self._base_url + titleEv.find('a', href=True)['href'])

        self._RAW_EVENTS = dict_events

    def _get_recent_birthdays_json(self):
        with open('sioux_birthdays.json', 'r') as fp:
            json_dump = json.load(fp)

            i = 0
            for date in json_dump['Date']:
                json_dump['Date'][i] = datetime.strptime(date, "%Y-%m-%d").date()
                i = i + 1

            self._RAW_BDAYS = json_dump

    def _get_recent_birthdays_https(self):
        """
        Get all recent birthdays from the bday page and store it in the member _RAW_BDAYS.\n

        :return: None\n
        """
        parseable_text = self._fetch_data(self._birtdayUrl)

        soup = BeautifulSoup(parseable_text, "html.parser")

        dict_bday = {'Name': [], 'Date': [], 'Role': [], 'RelativeTime': [], 'Url': []}

        bday = soup.find_all(self._bday_parse_element, {self._bday_parse_arg: self._bday_parse_overall})
        bdaylist = bday[0].findAll(self._bday_parse_separate)
        curr_year = self._curr_year
        curr_date = datetime(curr_year, self._curr_month, self._curr_day).date()

        position_today = parseable_text.find(self._bday_today)
        position_future = parseable_text.find(self._bday_future)
        position_past = parseable_text.find(self._bday_past)

        for entry in bdaylist:
            position_entry = parseable_text.find(entry.text)
            if position_today < position_entry < position_future:
                dict_bday['RelativeTime'].append(self._TODAY)
            elif position_future < position_entry < position_past:
                dict_bday['RelativeTime'].append(self._FUTURE)
            elif position_past < position_entry:
                dict_bday['RelativeTime'].append(self._PAST)
            else:
                raise RuntimeError(' Parsing bday day failed.')

            name = re.findall("(.+) \(", entry.text)[0]
            role = entry['class'][0]

            if dict_bday['RelativeTime'][-1] == self._TODAY:
                dict_bday['Date'].append(curr_date)
            else:
                # Some browsers retrieve (Nov 16), (May 16), ... instead of (16 Nov), (Mei 16), ...
                regex_date = re.findall("\(.+\)", entry.text)[0].replace('(', '').replace(')', '')
                if regex_date[0].isdigit():  # If we have a date that starts with a digit, we have a dutch date
                    date = datetime.strptime(regex_date, "%d %b").date().replace(year=curr_year)
                else:
                    locale.setlocale(locale.LC_TIME, 'en_US')
                    date = datetime.strptime(regex_date, "%b %d").date().replace(year=curr_year)
                    locale.setlocale(locale.LC_TIME, 'nl_BE')
                dict_bday['Date'].append(date)

            dict_bday['Url'].append(self._base_url + entry.get('href'))
            dict_bday['Name'].append(name)
            dict_bday['Role'].append(role)

        self._RAW_BDAYS = dict_bday

    def _get_persons_age(self, url):
        """
        Get age of a person given the persons url.\n

        :return: Age\n
        """
        parseable_text = self._fetch_data(url)

        curr_date = self._curr_date

        soup = BeautifulSoup(parseable_text, "html.parser")

        tab = soup.find(self._p_d_tab, {self._p_d_tab_arg: self._p_d_tab_value})
        rec = tab.find(self._p_d_rec_element, {self._p_d_rec_arg: self._p_d_rec_value})
        date = rec.find(self._p_d_date_element, {self._p_d_date_arg: self._p_d_date_value}).text
        dt = datetime.strptime(date, "%d-%m-%Y").date()

        # noinspection PyTypeChecker
        return curr_date.year - dt.year - ((curr_date.month, curr_date.day) < (dt.month, dt.day))

    def _validate_day(self, days, filter_days):
        """
        Validates given days based on the filter created in filter_events_date method.\n

        :param days:        List of days in datetime.date format.\n
        :param filter_days: Filter to apply on days.\n
        :return: True if dates respect filter settings, False otherwise. (boolean)\n
        """
        if days is None:
            raise RuntimeError('Event has no date!')

        current_date = self._curr_date

        if len(days) == 1:
            multiple_days = False
        else:
            multiple_days = len(days) > 1 and (days[0] != days[1])
        one_day = not multiple_days

        if (not filter_days[self._ONE_DAY] and one_day) or (not filter_days[self._MUL_DAY] and multiple_days):
            return False

        if not filter_days[self._PAST] and days[-1] < current_date:
            return False

        if not filter_days[self._FUTURE] and days[-1] > current_date:
            return False

        if not filter_days[self._TODAY] and days[0] <= current_date <= days[-1]:
            return False

        if (filter_days[self._ONE_DAY] and one_day) or (filter_days[self._MUL_DAY] and multiple_days):
            return True

        if filter_days[self._TODAY] and days[0] <= current_date <= days[-1]:
            return True

        if filter_days[self._FUTURE] and days[-1] > current_date:
            return True

        if filter_days[self._PAST] and days[-1] < current_date:
            return True

        return False

    def authenticate(self, host=None):
        """
        Authenticate using netrc file.\n

        :param host: Machine entry in ~/.netrc file for Sioux BE intranet. (string) (default 'siouxehv.nl')\n
        :return: None\n
        """
        if host is None:
            host = self._iis_domain

        secrets = netrc.netrc()
        ret = secrets.authenticators(host)
        if ret is None:
            raise RuntimeError("Invalid host provided!")

        username, _, password = ret
        username = self._iis_domain + '\\' + username

        self._session = requests.Session()
        self._session.auth = HttpNtlmAuth(username, password)

    def get_base_url(self):
        """
        Getter for the intranet base URL.\n

        :return: Base URL. (string)\n
        """
        return self._baseIntraUrl

    def get_events_overview_url(self):
        """
        Getter for the events overview URL.\n

        :return: Events overview URL. (string)\n
        """
        return self._eventsOverviewUrl

    def get_next_event(self, filter_cat, filter_date, filter_title=""):
        """
        Parse and filter the first event into a dictionary.\n

        :param filter_cat:   Filter created in method filter_events_category.\n
        :param filter_date:  Filter created in method filter_events_date.\n
        :param filter_title: Substring that is required in event title.\n
        :return: Next event. (Dictionary with keys: date, title, location, category)\n
        """
        events = self.parse_events(filter_cat, filter_date, filter_title)
        return events[0] if len(events) else []

    def filter_events_category(self, social_partner, social_colleague, powwow, training, exp_group, presentation):
        """
        Creates a filter to be used in the parse_events method.\n

        :param social_partner:   Include socials with partner. (boolean)\n
        :param social_colleague: Include socials with colleague. (boolean)\n
        :param powwow:           Include powwows. (boolean)\n
        :param training:         Include trainings. (boolean)\n
        :param exp_group:        Include expertise group meetings. (boolean)\n
        :param presentation:     Include presentations\n
        :return: Events filter bases on categories. (Dictionary with event categories as a key and their respective boolean argument as value.)\n
        """
        d = dict.fromkeys([self._evCatSocialPartner, self._evCatSocialColleague, self._evCatPowwow, self._evCatTraining, self._evCatExpGroup, self._evPresentation])
        d[self._evCatSocialPartner] = social_partner
        d[self._evCatSocialColleague] = social_colleague
        d[self._evCatPowwow] = powwow
        d[self._evCatTraining] = training
        d[self._evCatExpGroup] = exp_group
        d[self._evPresentation] = presentation

        return d

    def filter_events_date(self, one_day, mul_day, today, future, past):
        """
        Creates a filter to be used in the parse_events method.\n

        :param one_day: Include single day events. (boolean)\n
        :param mul_day: Include events that span over multiple days. (boolean)\n
        :param today:   Include today's events. (boolean)\n
        :param future:  Include future events. (boolean)\n
        :param past:    Include events that already happened. (boolean)\n
        :return: Events filter based on date requirements. (Dictionary with date filters as a key and their respective boolean argument as value.)\n
        """
        return {self._ONE_DAY: one_day, self._MUL_DAY: mul_day, self._TODAY: today, self._FUTURE: future, self._PAST: past}

    def filter_bday(self, today, future, past, age):
        """
        Creates a filter to be used in the parse_birthdays method.\n

        :param today:  Include today's birthdays. (boolean)\n
        :param future: Include future birthdays. (boolean)\n
        :param past:   Include birthdays that already happened. (boolean)\n
        :param age:    Include new age\n
        :return: Bday filters based on date requirements. (List)\n
        """
        filter_bday = []

        if today:
            filter_bday.append(self._TODAY)
        if future:
            filter_bday.append(self._FUTURE)
        if past:
            filter_bday.append(self._PAST)
        if age:
            filter_bday.append(self._AGE)

        return filter_bday

    def parse_events(self, filter_cat, filter_date, filter_title=""):
        """
        Parse and filter all events into a list of dictionaries.\n

        :param filter_cat:   Filter created in method filter_events_category.\n
        :param filter_date:  Filter created in method filter_events_date.\n
        :param filter_title: Substring that is required in event title.\n
        :return: Events (List of dictionaries with keys: date, title, location, category, url.)\n
        """
        results = []

        if self._RAW_EVENTS is None:
            self._get_events()

        events = self._RAW_EVENTS
        for i in range(len(events['Date'])):
            if not (filter_title in events['Title'][i] and filter_cat[events['Cat'][i]] and self._validate_day(events['Date'][i], filter_date)):
                continue
            if len(events['Date'][i]) == 2 and events['Date'][i][0] != events['Date'][i][1]:
                time = events['Date'][i][0].strftime('%d/%m/%Y') + " - " + events['Date'][i][1].strftime('%d/%m/%Y')
            elif len(events['Date'][i]) == 1 or events['Date'][i][0] == events['Date'][i][1]:
                time = events['Date'][i][0].strftime('%d/%m/%Y')
            else:
                time = None
            result = {'date': time, 'title': events['Title'][i], 'location': events['Loc'][i], 'category': events['Cat'][i], 'url': events['Url'][i]}
            results.append(result)
        return results

    def parse_birthdays(self, filter_bday):
        """
        Parse and filter all birthdays into a list of dictionaries.\n

        :param filter_bday: Filter created in method filter_bday.\n
        :return: Birthdays (List of dictionaries with keys: name, date, role, url, [new age].)\n
        """
        results = []

        if self._RAW_BDAYS is None:
            self._get_recent_birthdays()

        bdays = self._RAW_BDAYS

        for i in range(len(bdays['Date'])):
            if bdays['RelativeTime'][i] in filter_bday:
                if self._AGE in filter_bday:
                    temp_age = self._get_persons_age(bdays['Url'][i])
                    if bdays['Role'][i] == self._bday_collegue:
                        age = (temp_age if not bdays['RelativeTime'][i] == self._FUTURE else temp_age + 1)  # age should reflect how old someone will become this year.
                    else:
                        age = -1
                    result = {'name': bdays['Name'][i], 'date': bdays['Date'][i].strftime('%d/%m/%Y'),
                              'role': bdays['Role'][i], 'url': bdays['Url'][i], 'age': age}
                else:
                    result = {'name': bdays['Name'][i], 'date': bdays['Date'][i].strftime('%d/%m/%Y'),
                              'role': bdays['Role'][i], 'url': bdays['Url'][i]}
                results.append(result)
        return results


# Main program:
if __name__ == "__main__":
    # parser = SiouxParser(config_input=ConfigInput.dynamodb, data_input=DataInput.json)
    parser = SiouxParser(config_input=ConfigInput.netrc, data_input=DataInput.https)

    # Set filters
    get_age = False
    filter_category_dict = parser.filter_events_category(social_partner=True, social_colleague=True, powwow=True, training=True, exp_group=True, presentation=True)
    filter_date_dict = parser.filter_events_date(one_day=True, mul_day=True, today=True, future=True, past=False)
    filter_bday_dict = parser.filter_bday(today=False, future=True, past=False, age=get_age)

    # Retrieve events
    events_dict = parser.parse_events(filter_category_dict, filter_date_dict)
    # events = parser.get_next_event(filter_category_dict, filter_date_dict, "in the cloud")

    # Retrieve birthdays
    bday_dict = parser.parse_birthdays(filter_bday_dict)

    for event in events_dict:
        print 'Title: \t\t%s' % event['title']
        print 'Date: \t\t%s' % event['date']
        print 'Location: \t%s' % event['location']
        print 'Category: \t%s' % event['category']
        print 'Url: \t\t%s' % event['url']
        print ''

    for birthday in bday_dict:
        print 'Name: \t%s' % birthday['name']
        print 'Date: \t%s' % birthday['date']
        print 'Role: \t%s' % birthday['role']
        print 'Url: \t%s' % birthday['url']
        if get_age:
            print 'Age: \t%s' % birthday['age']
        print ''
