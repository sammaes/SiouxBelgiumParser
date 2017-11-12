#!/usr/bin/python

import locale
import netrc
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


def prettify_string(string):
    """
    Remove tabs and newlines from string.
    Returns prettified string.
    """
    return string.replace('\n', '').replace('\t', '')


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
    """Parser for Sioux BE intranet."""

    def __init__(self):
        self.conf = ConfigParser.ConfigParser()
        self.conf.read('config.ini')

        self.__iis_domain = self.conf.get('URLS', 'IIS_DOMAIN')
        self.__baseUrl = self.conf.get('URLS', 'BASE')
        self.__eventsUrl = self.__baseUrl + self.conf.get('URLS', 'EVENTS_EXT')
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
    def validate_day(days, filter_date):
        """
        Validates given days based on the filter created in filter_events_date method.
        Returns true if dates respect filter settings, false otherwise.
        """
        if days is None:
            raise RuntimeError('Event has no date!')

        current_date = datetime.now().date()
        multiple_days = len(days) > 1 and (days[0] != days[1])

        if (not filter_date[ONE_DAY] and not multiple_days) or (not filter_date[MUL_DAY] and not multiple_days):
            return False

        if not filter_date[PAST] and days[-1] < current_date:
            return False

        if not filter_date[FUTURE] and days[-1] > current_date:
            return False

        if (filter_date[ONE_DAY] and not multiple_days) or (filter_date[MUL_DAY] and multiple_days):
            return True

        if filter_date[TODAY] and days[0] <= current_date <= days[-1]:
            return True

        if filter_date[FUTURE] and days[-1] > current_date:
            return True

        if filter_date[PAST] and days[-1] < current_date:
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

    def get_events(self, filter_cat, filter_date):
        """
        Get all events from the events page.

        Keyword arguments:
        filter_cat -- dictionary created by filter_events_category method.
        """
        if self.__session is None:
            raise RuntimeError('Not authenticated yet. Call authenticate method before getting events!')

        parse_element = self.conf.get('PARSE_EV', 'ELEMENT')
        parse_arg = self.conf.get('PARSE_EV', 'ARG')
        req = self.__session.get(self.__eventsUrl)
        soup = BeautifulSoup(req.content, "html.parser")

        dict_events = {"Dates": [], "Titles": [], "Location": [], "Category": []}

        dates = [parse_date(datee.text) for datee in soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_DATE')})]
        titles = soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_TITLE')})
        location = soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_LOCATION')})
        category = [prettify_string(catt.text) for catt in soup.find_all(parse_element, {parse_arg: self.conf.get('PARSE_EV', 'VALUE_CATEGORY')})]

        for dateEv, titleEv, locEv, catEv in zip(dates, titles, location, category):
            if filter_cat[catEv] and self.validate_day(dateEv, filter_date):
                dict_events['Dates'].append(dateEv)
                dict_events['Titles'].append(prettify_string(titleEv.text))
                dict_events['Location'].append(prettify_string(locEv.text))
                dict_events['Category'].append(catEv)

        return dict_events


# Main program:
if __name__ == "__main__":
    parser = SiouxParser()
    parser.authenticate()
    events = None
    try:
        events = parser.get_events(parser.filter_events_category(social_partner=True, social_colleague=True, powwow=True, training=True, exp_group=True),
                                   parser.filter_events_date(one_day=False, mul_day=True, today=True, future=True, past=False))
    except RuntimeError as err:
        print err.args[0]
        exit(1)

    for date, title, loc, cat in zip(events['Dates'],
                                     events['Titles'],
                                     events['Location'],
                                     events['Category']):
        if len(date) == 2 and date[0] != date[1]:
            print "Meerdere dagen: Start:" + date[0].strftime('%d/%m/%Y') + " Stop:" + date[1].strftime('%d/%m/%Y')
        elif len(date) == 1 or date[0] == date[1]:
            print "1 Dag:" + date[0].strftime('%d/%m/%Y')

        print 'Titel: ' + title
        print 'Locatie: ' + loc
        print 'Categorie: ' + cat
        print '\n'
