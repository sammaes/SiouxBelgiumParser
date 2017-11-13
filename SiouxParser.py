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
    Remove tabs, newlines and leading/trailing spaces from string.
    Returns prettified string.
    """
    return string.strip().replace('\n', '').replace('\t', '')


def parse_date(string):
    """
    Parse string to find all dates.
    Returns a list of dates in datetime.date format.
    """
    m = re.findall("\d\d +[a-z]+ '\d\d", string)
    if m:
        return [datetime.strptime(dateString, "%d %b '%y").date() for dateString in m]
    else:
        return None


class SiouxParser:
    RAW_EVENTS = None
    RAW_BDAYS = None

    def __init__(self, path_config_file=None):
        """
        Parser for Sioux BE intranet.

        Keyword arguments:
        path_config_file -- path to the configuration file (default: current directory)
        """
        self.conf = ConfigParser.ConfigParser()

        path = path_config_file if path_config_file is not None else os.getcwd()
        config_file = os.path.join(path, CONFIG_FILE)

        if os.path.isfile(config_file):
            self.conf.read(config_file)
        else:
            raise RuntimeError("Could not locate config file '%s'." % config_file)

        self.__iis_domain = self.conf.get('URLS', 'IIS_DOMAIN')
        self.__baseUrl = self.conf.get('URLS', 'BASE')
        self.__eventsOverviewUrl = self.__baseUrl + self.conf.get('URLS', 'EVENTS_OVERVIEW_EXT')
        self.__birtdayUrl = self.__baseUrl + self.conf.get('URLS', 'BDAY_EXT')
        self.__session = None

        # Event categories:
        self.__evCatSocialPartner = self.conf.get('EVENTS', 'SOCIAL_PARTNER')
        self.__evCatSocialColleague = self.conf.get('EVENTS', 'SOCIAL_COLLEAGUE')
        self.__evCatPowwow = self.conf.get('EVENTS', 'POWWOW')
        self.__evCatTraining = self.conf.get('EVENTS', 'TRAINING')
        self.__evCatExpGroup = self.conf.get('EVENTS', 'EXP_GROUP')

        locale.setlocale(locale.LC_TIME, "nl_BE")

    def filter_events_category(self, social_partner, social_colleague, powwow, training, exp_group):
        """
        Creates a filter to be used in the get_events method.
        Returns a dictionary with event categories as a key and their respective boolean argument as value.

        Keyword arguments:
        social_partner   -- include socials with partner (boolean)
        social_colleague -- include socials with colleague (boolean)
        powwow           -- include powwows (boolean)
        training         -- include trainings (boolean)
        exp_group        -- include expertise group meetings (boolean)
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
        Creates a filter to be used in the get_events method.
        Returns a dictionary with date filters as a key and their respective boolean argument as value.

        Keyword arguments:
        one_day -- include single day events (boolean)
        mul_day -- include events that span over multiple days (boolean)
        today   -- include today's events (boolean)
        future  -- include future events (boolean)
        past    -- include events that already happened (boolean)
        """
        return {ONE_DAY: one_day, MUL_DAY: mul_day, TODAY: today, FUTURE: future, PAST: past}

    @staticmethod
    def __validate_day(days, filter_days):
        """
        Validates given days based on the filter created in filter_events_date method.
        Returns true if dates respect filter settings, false otherwise.
        """
        if days is None:
            raise RuntimeError('Event has no date!')

        current_date = datetime.now().date()
        multiple_days = len(days) > 1 and (days[0] != days[1])

        if (not filter_days[ONE_DAY] and not multiple_days) or (not filter_days[MUL_DAY] and not multiple_days):
            return False

        if not filter_days[PAST] and days[-1] < current_date:
            return False

        if not filter_days[FUTURE] and days[-1] > current_date:
            return False

        if (filter_days[ONE_DAY] and not multiple_days) or (filter_days[MUL_DAY] and multiple_days):
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

        Keyword arguments:
        machine -- machine entry in ~/.netrc file for Sioux BE intranet (string) (default 'siouxehv.nl')
        """
        if machine is None:
            machine = self.__iis_domain

        secrets = netrc.netrc()
        username, _, password = secrets.authenticators(machine)
        username = self.__iis_domain + '\\' + username

        self.__session = requests.Session()
        self.__session.auth = HttpNtlmAuth(username, password)

    def __get_events(self):
        """
        Get all events from the events page and store it in the member RAW_EVENTS
        """
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting events!')

        events_base_url = self.conf.get('URLS', 'EVENTS_EXT')
        parse_element = self.conf.get('PARSE_EV', 'ELEMENT')
        parse_arg = self.conf.get('PARSE_EV', 'ARG')
        req = self.__session.get(self.__eventsOverviewUrl)
        soup = BeautifulSoup(req.content, "html.parser")

        dict_events = {"Dates": [], "Titles": [], "Location": [], "Category": [], "Url": []}

        dates = [parse_date(datee.text) for datee in soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_DATE')})]
        titles = soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_TITLE')})
        location = soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_LOCATION')})
        category = [prettify_string(catt.text) for catt in soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_CATEGORY')})]

        for dateEv, titleEv, locEv, catEv in zip(dates, titles, location, category):
            dict_events['Dates'].append(dateEv)
            dict_events['Titles'].append(prettify_string(titleEv.text))
            dict_events['Location'].append(prettify_string(locEv.text))
            dict_events['Category'].append(catEv)
            dict_events['Url'].append(events_base_url + titleEv.find('a', href=True)['href'])

        self.RAW_EVENTS = dict_events

    def parse_events(self, filter_cat, filter_date, filter_title=""):
        """
        Parse and filter all events into a list of dictionaries.
        Returns: List of dictionaries with keys: date, title, location, category.
        """
        results = []

        if self.RAW_EVENTS is None:
            self.__get_events()

        events = self.RAW_EVENTS

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

    def get_next_event(self, filter_cat, filter_date, filter_title=""):
        """
        Parse and filter the first event into a dictionary.
        Returns: Dictionary with keys: date, title, location, category.
        """
        events = self.parse_events(filter_cat, filter_date, filter_title)
        return events[0] if len(events) else []

    def __get_recent_birthdays(self):
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting events!')

        bdays = []

        req = self.__session.get(self.__birtdayUrl)
        soup = BeautifulSoup(req.content)

        bday = soup.find_all(self.conf.get('PARSE_BDAY', 'ELEMENT'), {self.conf.get('PARSE_BDAY', 'ARG'): self.conf.get('PARSE_BDAY', 'VALUE_OVERALL')})
        bdaylist = bday[0].findAll(self.conf.get('PARSE_BDAY', 'VALUE_SEPARATE'))
        for entry in bdaylist:
            regex_name = re.findall("(.+) \(", entry.text)
            regex_date = re.findall("\((\d{1,2} [a-z]+)\)", entry.text)

            name = regex_name[0]
            role = entry['class'][0]
            date = datetime.strptime(regex_date[0], "%d %b").date().replace(year=datetime.now().date().year)

            result = {'name': name, 'date': date, 'role': role}
            bdays.append(result)

        self.RAW_BDAYS = bdays


# Main program:
if __name__ == "__main__":
    parser = SiouxParser()
    parser.authenticate()

    # Set filters
    filter_category_dict = parser.filter_events_category(social_partner=True, social_colleague=True, powwow=True, training=True, exp_group=True)
    filter_date_dict = parser.filter_events_date(one_day=True, mul_day=True, today=True, future=True, past=False)

    # Retrieve events
    events_dict = parser.parse_events(filter_category_dict, filter_date_dict)
    # events = parser.get_next_event(filter_category_dict, filter_date_dict, "in the cloud")

    for event in events_dict:
        print 'Title: \t\t%s' % event['title']
        print 'Date: \t\t%s' % event['date']
        print 'Location: \t%s' % event['location']
        print 'Category: \t%s' % event['category']
        print 'Url: \t\t%s' % event['url']
        print ''
