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

# Filter keys for event date
ONE_DAY = 'one_day'
MUL_DAY = 'multiple_days'
TODAY = 'today'
FUTURE = 'future'
PAST = 'past'

# Config file
CONFIG_FILE = 'config.ini'


def prettify_string(string):
    """
    Remove tabs, newlines and leading/trailing spaces.

    :param string: String containing clutter.
    :return: Prettified string. (string)
    """
    return string.strip().replace('\n', '').replace('\t', '')


def parse_event_date(string):
    """
    Parse a string to find all event dates.

    :param string: Human readable date.
    :return: Dates (List of datetime.date)
    """
    m = re.findall("\d\d +[a-z]+ '\d\d", string)
    if m:
        return [datetime.strptime(dateString, "%d %b '%y").date() for dateString in m]
    else:
        return None


class SiouxParser:
    __RAW_EVENTS = None
    __RAW_BDAYS = None

    def __init__(self, path_config_file=None):
        """
        Parser for Sioux BE intranet.

        :param path_config_file: Path to the configuration file. (default: current directory)
        """
        self.__conf = ConfigParser.ConfigParser()

        path = path_config_file if path_config_file is not None else os.getcwd()
        config_file = os.path.join(path, CONFIG_FILE)

        if os.path.isfile(config_file):
            self.__conf.read(config_file)
        else:
            raise RuntimeError("Could not locate config file '%s'." % config_file)

        self.__iis_domain = self.__get_config('URLS', 'IIS_DOMAIN')
        self.__baseUrl = self.__get_config('URLS', 'BASE')
        self.__eventsOverviewUrl = self.__baseUrl + self.__get_config('URLS', 'EVENTS_OVERVIEW_EXT')
        self.__birtdayUrl = self.__baseUrl + self.__get_config('URLS', 'BDAY_EXT')
        self.__session = None

        # Event categories:
        self.__evCatSocialPartner = self.__get_config('EVENTS', 'SOCIAL_PARTNER')
        self.__evCatSocialColleague = self.__get_config('EVENTS', 'SOCIAL_COLLEAGUE')
        self.__evCatPowwow = self.__get_config('EVENTS', 'POWWOW')
        self.__evCatTraining = self.__get_config('EVENTS', 'TRAINING')
        self.__evCatExpGroup = self.__get_config('EVENTS', 'EXP_GROUP')

        locale.setlocale(locale.LC_TIME, "nl_BE")

    def __get_config(self, key, value):
        """
        Get configuration value from config file.

        :param key:   Key found in configuration value. (string)
        :param value: Value associated with said key. (string)
        :return: Configuration value. (string)
        """
        return self.__conf.get(key, value)

    def __get_events(self):
        """
        Get all events from the events page and store it in member __RAW_EVENTS.

        :return: None
        """
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting events!')

        events_base_url = self.__get_config('URLS', 'EVENTS_EXT')
        parse_element = self.__get_config('PARSE_EV', 'ELEMENT')
        parse_arg = self.__get_config('PARSE_EV', 'ARG')
        req = self.__session.get(self.__eventsOverviewUrl)
        soup = BeautifulSoup(req.text, "html.parser")

        dict_events = {"Dates": [], "Titles": [], "Location": [], "Category": [], "Url": []}

        dates = [parse_event_date(datee.text) for datee in soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_DATE')})]
        titles = soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_TITLE')})
        location = soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_LOCATION')})
        category = [prettify_string(catt.text) for catt in soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_CATEGORY')})]

        for dateEv, titleEv, locEv, catEv in zip(dates, titles, location, category):
            dict_events['Dates'].append(dateEv)
            dict_events['Titles'].append(prettify_string(titleEv.text))
            dict_events['Location'].append(prettify_string(locEv.text))
            dict_events['Category'].append(catEv)
            dict_events['Url'].append(events_base_url + titleEv.find('a', href=True)['href'])

        self.__RAW_EVENTS = dict_events

    def __get_recent_birthdays(self):
        """
        Get all recent birthdays from the bday page and store it in the member __RAW_BDAYS.

        :return: None
        """
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting events!')

        req = self.__session.get(self.__birtdayUrl)
        soup = BeautifulSoup(req.text, "html.parser")

        position_today = req.text.find(self.__get_config('PARSE_BDAY', 'TITLE_TODAY'))
        position_future = req.text.find(self.__get_config('PARSE_BDAY', 'TITLE_FUTURE'))
        position_past = req.text.find(self.__get_config('PARSE_BDAY', 'TITLE_PAST'))
        dict_bday = {'Name': [], 'Date': [], 'Role': [], 'RelativeTime': []}

        bday = soup.find_all(self.__get_config('PARSE_BDAY', 'ELEMENT'), {self.__get_config('PARSE_BDAY', 'ARG'): self.__get_config('PARSE_BDAY', 'VALUE_OVERALL')})
        bdaylist = bday[0].findAll(self.__get_config('PARSE_BDAY', 'VALUE_SEPARATE'))

        for entry in bdaylist:
            if position_today < req.text.find(entry.text) < position_future:
                dict_bday['RelativeTime'].append(TODAY)
            elif position_future < req.text.find(entry.text) < position_past:
                dict_bday['RelativeTime'].append(FUTURE)
            elif position_past < req.text.find(entry.text):
                dict_bday['RelativeTime'].append(PAST)
            else:
                raise RuntimeError(' Parsing bday day failed.')

            name = re.findall("(.+) \(", entry.text)[0]
            role = entry['class'][0]

            # Some browsers retrieve (Nov 16), (May 16), ... instead of (16 Nov), (Mei 16), ...
            regex_date = re.findall("\(.+\)", entry.text)[0].replace('(', '').replace(')', '')
            if regex_date[0].isdigit():  # If we have a date that starts with a digit, we have a dutch date
                date = datetime.strptime(regex_date, "%d %b").date().replace(year=datetime.now().date().year)
            else:
                locale.setlocale(locale.LC_TIME, 'en_US')
                date = datetime.strptime(regex_date, "%b %d").date().replace(year=datetime.now().date().year)
                locale.setlocale(locale.LC_TIME, 'nl_BE')

            dict_bday['Name'].append(name)
            dict_bday['Date'].append(date)
            dict_bday['Role'].append(role)

        self.__RAW_BDAYS = dict_bday

    @staticmethod
    def __validate_day(days, filter_days):
        """
        Validates given days based on the filter created in filter_events_date method.

        :param days:        List of days in datetime.date format.
        :param filter_days: Filter to apply on days.
        :return: True if dates respect filter settings, False otherwise. (boolean)
        """
        if days is None:
            raise RuntimeError('Event has no date!')

        current_date = datetime.now().date()

        if len(days) == 1:
            multiple_days = False
        else:
            multiple_days = len(days) > 1 and (days[0] != days[1])
        one_day = not multiple_days

        if (not filter_days[ONE_DAY] and one_day) or (not filter_days[MUL_DAY] and multiple_days):
            return False

        if not filter_days[PAST] and days[-1] < current_date:
            return False

        if not filter_days[FUTURE] and days[-1] > current_date:
            return False

        if not filter_days[TODAY] and days[0] <= current_date <= days[-1]:
            return False

        if (filter_days[ONE_DAY] and one_day) or (filter_days[MUL_DAY] and multiple_days):
            return True

        if filter_days[TODAY] and days[0] <= current_date <= days[-1]:
            return True

        if filter_days[FUTURE] and days[-1] > current_date:
            return True

        if filter_days[PAST] and days[-1] < current_date:
            return True

        return False

    def authenticate(self, machine=None):
        """
        Authenticate using netrc file.

        :param machine: Machine entry in ~/.netrc file for Sioux BE intranet. (string) (default 'siouxehv.nl')
        :return: None
        """
        if machine is None:
            machine = self.__iis_domain

        secrets = netrc.netrc()
        username, _, password = secrets.authenticators(machine)
        username = self.__iis_domain + '\\' + username

        self.__session = requests.Session()
        self.__session.auth = HttpNtlmAuth(username, password)

    def get_base_url(self):
        """
        Getter for the intranet base URL.

        :return: Base URL. (string)
        """
        return self.__baseUrl

    def get_events_overview_url(self):
        """
        Getter for the events overview URL.

        :return: Events overview URL. (string)
        """
        return self.__eventsOverviewUrl

    def get_next_event(self, filter_cat, filter_date, filter_title=""):
        """
        Parse and filter the first event into a dictionary.

        :param filter_cat:   Filter created in method filter_events_category.
        :param filter_date:  Filter created in method filter_events_date.
        :param filter_title: Substring that is required in event title.
        :return: Next event. (Dictionary with keys: date, title, location, category)
        """
        events = self.parse_events(filter_cat, filter_date, filter_title)
        return events[0] if len(events) else []

    def filter_events_category(self, social_partner, social_colleague, powwow, training, exp_group):
        """
        Creates a filter to be used in the parse_events method.

        :param social_partner:   Include socials with partner. (boolean)
        :param social_colleague: Include socials with colleague. (boolean)
        :param powwow:           Include powwows. (boolean)
        :param training:         Include trainings. (boolean)
        :param exp_group:        Include expertise group meetings. (boolean)
        :return: Events filter bases on categories. (Dictionary with event categories as a key and their respective boolean argument as value.)
        """
        d = dict.fromkeys([self.__evCatSocialPartner, self.__evCatSocialColleague, self.__evCatPowwow, self.__evCatTraining, self.__evCatExpGroup])
        d[self.__evCatSocialPartner] = social_partner
        d[self.__evCatSocialColleague] = social_colleague
        d[self.__evCatPowwow] = powwow
        d[self.__evCatTraining] = training
        d[self.__evCatExpGroup] = exp_group

        return d

    @staticmethod
    def filter_events_date(one_day, mul_day, today, future, past):
        """
        Creates a filter to be used in the parse_events method.

        :param one_day: Include single day events. (boolean)
        :param mul_day: Include events that span over multiple days. (boolean)
        :param today:   Include today's events. (boolean)
        :param future:  Include future events. (boolean)
        :param past:    Include events that already happened. (boolean)
        :return: Events filter based on date requirements. (Dictionary with date filters as a key and their respective boolean argument as value.)
        """
        return {ONE_DAY: one_day, MUL_DAY: mul_day, TODAY: today, FUTURE: future, PAST: past}

    @staticmethod
    def filter_bday(today, future, past):
        """
        Creates a filter to be used in the parse_birthdays method.

        :param today:  Include today's birthdays. (boolean)
        :param future: Include future birthdays. (boolean)
        :param past:   Include birthdays that already happened. (boolean)
        :return: Bday filters based on date requirements. (List)
        """
        filter_bday = []

        if today:
            filter_bday.append(TODAY)
        if future:
            filter_bday.append(FUTURE)
        if past:
            filter_bday.append(PAST)

        return filter_bday

    def parse_events(self, filter_cat, filter_date, filter_title=""):
        """
        Parse and filter all events into a list of dictionaries.

        :param filter_cat:   Filter created in method filter_events_category.
        :param filter_date:  Filter created in method filter_events_date.
        :param filter_title: Substring that is required in event title.
        :return: Events (List of dictionaries with keys: date, title, location, category, url.)
        """
        results = []

        if self.__RAW_EVENTS is None:
            self.__get_events()

        events = self.__RAW_EVENTS

        for date, title, loc, cat, url in zip(events['Dates'], events['Titles'], events['Location'], events['Category'], events['Url']):
            if not (filter_title in title and filter_cat[cat] and self.__validate_day(date, filter_date)):
                continue
            if len(date) == 2 and date[0] != date[1]:
                time = date[0].strftime('%d/%m/%Y') + " - " + date[1].strftime('%d/%m/%Y')
            elif len(date) == 1 or date[0] == date[1]:
                time = date[0].strftime('%d/%m/%Y')
            else:
                time = None
            result = {'date': time, 'title': title, 'location': loc, 'category': cat, 'url': url}
            results.append(result)
        return results

    def parse_birthdays(self, filter_bday):
        """
        Parse and filter all birthdays into a list of dictionaries.

        :param filter_bday: Filter created in method filter_bday.
        :return: Birthdays (List of dictionaries with keys: name, date, role.)
        """
        results = []

        if self.__RAW_BDAYS is None:
            self.__get_recent_birthdays()

        bdays = self.__RAW_BDAYS

        for name, date, role, rel_time in zip(bdays['Name'], bdays['Date'], bdays['Role'], bdays['RelativeTime']):
            if rel_time in filter_bday:
                result = {'name': name, 'date': date.strftime('%d/%m/%Y'), 'role': role}
                results.append(result)
        return results


# Main program:
if __name__ == "__main__":
    parser = SiouxParser()
    parser.authenticate()

    # Set filters
    filter_category_dict = parser.filter_events_category(social_partner=True, social_colleague=True, powwow=True, training=True, exp_group=True)
    filter_date_dict = parser.filter_events_date(one_day=True, mul_day=True, today=True, future=True, past=False)
    filter_bday_dict = parser.filter_bday(today=True, future=True, past=False)

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
        print ''
