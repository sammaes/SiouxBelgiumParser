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


class SiouxParser:
    __RAW_EVENTS = None
    __RAW_BDAYS = None

    # Filter keys for event date
    __ONE_DAY = 'one_day'
    __MUL_DAY = 'multiple_days'
    __TODAY = 'today'
    __FUTURE = 'future'
    __PAST = 'past'

    # Config file
    __CONFIG_FILE = 'config.ini'

    def __init__(self, path_config_file=None):
        """
        Parser for Sioux BE intranet.\n

        :param path_config_file: Path to the configuration file. (default: current directory)\n
        """
        self.__conf = ConfigParser.ConfigParser()

        path = path_config_file if path_config_file is not None else os.getcwd()
        config_file = os.path.join(path, self.__CONFIG_FILE)

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

    @staticmethod
    def __prettify_string(string):
        """
        Remove tabs, newlines and leading/trailing spaces.\n

        :param string: String containing clutter.\n
        :return: Prettified string. (string)\n
        """
        return string.strip().replace('\n', '').replace('\t', '')

    @staticmethod
    def __parse_event_date(string):
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

    def __get_config(self, key, value):
        """
        Get configuration value from config file.\n

        :param key:   Key found in configuration value. (string)\n
        :param value: Value associated with said key. (string)\n
        :return: Configuration value. (string)\n
        """
        return self.__conf.get(key, value)

    def __get_events(self):
        """
        Get all events from the events page and store it in member __RAW_EVENTS.\n

        :return: None\n
        """
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting events!')

        events_base_url = self.__get_config('URLS', 'EVENTS_EXT')
        parse_element = self.__get_config('PARSE_EV', 'ELEMENT')
        parse_arg = self.__get_config('PARSE_EV', 'ARG')
        req = self.__session.get(self.__eventsOverviewUrl)
        soup = BeautifulSoup(req.text, "html.parser")

        dict_events = {"Dates": [], "Titles": [], "Location": [], "Category": [], "Url": []}

        dates = [self.__parse_event_date(datee.text) for datee in soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_DATE')})]
        titles = soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_TITLE')})
        location = soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_LOCATION')})
        category = [self.__prettify_string(catt.text) for catt in soup.find_all(parse_element, {parse_arg: self.__get_config('PARSE_EV', 'VALUE_CATEGORY')})]

        for dateEv, titleEv, locEv, catEv in zip(dates, titles, location, category):
            dict_events['Dates'].append(dateEv)
            dict_events['Titles'].append(self.__prettify_string(titleEv.text))
            dict_events['Location'].append(self.__prettify_string(locEv.text))
            dict_events['Category'].append(catEv)
            dict_events['Url'].append(events_base_url + titleEv.find('a', href=True)['href'])

        self.__RAW_EVENTS = dict_events

    def __get_recent_birthdays(self, test_content=None):
        """
        Get all recent birthdays from the bday page and store it in the member __RAW_BDAYS.\n

        :return: None\n
        """
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting birthdays!')

        req = self.__session.get(self.__birtdayUrl)

        parseable_text = req.text if test_content is None else test_content
        soup = BeautifulSoup(parseable_text, "html.parser")

        position_today = parseable_text.find(self.__get_config('PARSE_BDAY', 'TITLE_TODAY'))
        position_future = parseable_text.find(self.__get_config('PARSE_BDAY', 'TITLE_FUTURE'))
        position_past = parseable_text.find(self.__get_config('PARSE_BDAY', 'TITLE_PAST'))
        dict_bday = {'Name': [], 'Date': [], 'Role': [], 'RelativeTime': []}

        bday = soup.find_all(self.__get_config('PARSE_BDAY', 'ELEMENT'), {self.__get_config('PARSE_BDAY', 'ARG'): self.__get_config('PARSE_BDAY', 'VALUE_OVERALL')})
        bdaylist = bday[0].findAll(self.__get_config('PARSE_BDAY', 'VALUE_SEPARATE'))

        for entry in bdaylist:
            if position_today < parseable_text.find(entry.text) < position_future:
                dict_bday['RelativeTime'].append(self.__TODAY)
            elif position_future < parseable_text.find(entry.text) < position_past:
                dict_bday['RelativeTime'].append(self.__FUTURE)
            elif position_past < parseable_text.find(entry.text):
                dict_bday['RelativeTime'].append(self.__PAST)
            else:
                raise RuntimeError(' Parsing bday day failed.')

            name = re.findall("(.+) \(", entry.text)[0]
            role = entry['class'][0]

            if dict_bday['RelativeTime'][-1] == self.__TODAY:
                dict_bday['Date'] = datetime.now().date()
            else:
                # Some browsers retrieve (Nov 16), (May 16), ... instead of (16 Nov), (Mei 16), ...
                regex_date = re.findall("\(.+\)", entry.text)[0].replace('(', '').replace(')', '')
                if regex_date[0].isdigit():  # If we have a date that starts with a digit, we have a dutch date
                    date = datetime.strptime(regex_date, "%d %b").date().replace(year=datetime.now().date().year)
                else:
                    locale.setlocale(locale.LC_TIME, 'en_US')
                    date = datetime.strptime(regex_date, "%b %d").date().replace(year=datetime.now().date().year)
                    locale.setlocale(locale.LC_TIME, 'nl_BE')
                dict_bday['Date'].append(date)

            dict_bday['Name'].append(name)
            dict_bday['Role'].append(role)

        self.__RAW_BDAYS = dict_bday

    def __validate_day(self, days, filter_days):
        """
        Validates given days based on the filter created in filter_events_date method.\n

        :param days:        List of days in datetime.date format.\n
        :param filter_days: Filter to apply on days.\n
        :return: True if dates respect filter settings, False otherwise. (boolean)\n
        """
        if days is None:
            raise RuntimeError('Event has no date!')

        current_date = datetime.now().date()

        if len(days) == 1:
            multiple_days = False
        else:
            multiple_days = len(days) > 1 and (days[0] != days[1])
        one_day = not multiple_days

        if (not filter_days[self.__ONE_DAY] and one_day) or (not filter_days[self.__MUL_DAY] and multiple_days):
            return False

        if not filter_days[self.__PAST] and days[-1] < current_date:
            return False

        if not filter_days[self.__FUTURE] and days[-1] > current_date:
            return False

        if not filter_days[self.__TODAY] and days[0] <= current_date <= days[-1]:
            return False

        if (filter_days[self.__ONE_DAY] and one_day) or (filter_days[self.__MUL_DAY] and multiple_days):
            return True

        if filter_days[self.__TODAY] and days[0] <= current_date <= days[-1]:
            return True

        if filter_days[self.__FUTURE] and days[-1] > current_date:
            return True

        if filter_days[self.__PAST] and days[-1] < current_date:
            return True

        return False

    def authenticate(self, machine=None):
        """
        Authenticate using netrc file.\n

        :param machine: Machine entry in ~/.netrc file for Sioux BE intranet. (string) (default 'siouxehv.nl')\n
        :return: None\n
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
        Getter for the intranet base URL.\n

        :return: Base URL. (string)\n
        """
        return self.__baseUrl

    def get_events_overview_url(self):
        """
        Getter for the events overview URL.\n

        :return: Events overview URL. (string)\n
        """
        return self.__eventsOverviewUrl

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

    def filter_events_category(self, social_partner, social_colleague, powwow, training, exp_group):
        """
        Creates a filter to be used in the parse_events method.\n

        :param social_partner:   Include socials with partner. (boolean)\n
        :param social_colleague: Include socials with colleague. (boolean)\n
        :param powwow:           Include powwows. (boolean)\n
        :param training:         Include trainings. (boolean)\n
        :param exp_group:        Include expertise group meetings. (boolean)\n
        :return: Events filter bases on categories. (Dictionary with event categories as a key and their respective boolean argument as value.)\n
        """
        d = dict.fromkeys([self.__evCatSocialPartner, self.__evCatSocialColleague, self.__evCatPowwow, self.__evCatTraining, self.__evCatExpGroup])
        d[self.__evCatSocialPartner] = social_partner
        d[self.__evCatSocialColleague] = social_colleague
        d[self.__evCatPowwow] = powwow
        d[self.__evCatTraining] = training
        d[self.__evCatExpGroup] = exp_group

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
        return {self.__ONE_DAY: one_day, self.__MUL_DAY: mul_day, self.__TODAY: today, self.__FUTURE: future, self.__PAST: past}

    def filter_bday(self, today, future, past):
        """
        Creates a filter to be used in the parse_birthdays method.\n

        :param today:  Include today's birthdays. (boolean)\n
        :param future: Include future birthdays. (boolean)\n
        :param past:   Include birthdays that already happened. (boolean)\n
        :return: Bday filters based on date requirements. (List)\n
        """
        filter_bday = []

        if today:
            filter_bday.append(self.__TODAY)
        if future:
            filter_bday.append(self.__FUTURE)
        if past:
            filter_bday.append(self.__PAST)

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
        Parse and filter all birthdays into a list of dictionaries.\n

        :param filter_bday: Filter created in method filter_bday.\n
        :return: Birthdays (List of dictionaries with keys: name, date, role.)\n
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
