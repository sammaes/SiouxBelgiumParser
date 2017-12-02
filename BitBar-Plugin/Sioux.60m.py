#!/usr/bin/python
# -*- coding: utf-8 -*-
# to convert image on mac: cat /Users/kevin/Downloads/Sioux-logo-corporate.png  | openssl base64 | tr -d '\n' | pbcopy

import os
import sys
from datetime import datetime
from scripts.SiouxParser import SiouxParser
from scripts.SiouxParser import ConfigInput
from scripts.SiouxParser import DataInput

def print_menu_section(section_title, event, show_cat=False):
    menu_section_title = " font=HelveticaNeue size=10"
    menu_title = "color=black font=HelveticaNeue-Bold size=13 href=%s" % event['url']
    menu_details = "trim=false font=HelveticaNeue-Italic"
    print "%s | %s" % (section_title, menu_section_title)
    print "%s | %s" % (event['title'], menu_title)
    print "     %s | %s" % (datetime.strptime(event['date'], "%d/%m/%Y").strftime("%d %B %Y"), menu_details)
    print "     %s | %s" % (event['location'], menu_details)
    if show_cat:
        print "     %s | %s" % (event['category'], menu_details)
    print "---"

def print_bdays(section_title, bdays, limit, only_collegues=True):
    menu_section_title = "font=HelveticaNeue size=10"
    menu_details = "trim=false font=HelveticaNeue"
    number_printed = 0
    print "%s | %s" % (section_title, menu_section_title)
    for bday in bdays:
        if only_collegues and bday['role'] != 'collegue':
            continue
        print "%s - %s | %s" % (bday['name'], bday['date'], menu_details)
        number_printed = number_printed + 1
        if number_printed == limit:
            break
    print "---"

def contains_collegues(bdays):
    for bday in bdays:
        if bday['role'] == 'collegue':
            return True
        
sioux_sun = "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"

# Initilalise parser and authenticate
parser = SiouxParser(config_input=ConfigInput.netrc, data_input=DataInput.https, path_config_file=os.path.join(os.path.abspath(os.path.dirname(sys.argv[0])), 'scripts'))

# Set filters
filter_event = parser.filter_events_category(social_partner=True, social_colleague=True, powwow=True, training=True, exp_group=True)
filter_date = parser.filter_events_date(one_day=True, mul_day=True, today=False, future=True, past=False)
filter_bday_date = parser.filter_bday_date(today=True, future=True, past=False)
filter_bday_category = parser.filter_bday_category(collegue=True, child=True, partner=True, age=False)

# Get events
next_general_event = parser.get_next_event(filter_event, filter_date)
cloud_event = parser.get_next_event(filter_event, filter_date, "in the cloud")
linux_event = parser.get_next_event(filter_event, filter_date, "Linux Kennisdelen")
bdays = parser.parse_birthdays(filter_bday_category, filter_bday_date)

# These prints define the menu, starting with the visible text in the menu bar (in this case, an image)
print "| templateImage=%s" % sioux_sun
print "---"
if next_general_event != []:
    print_menu_section("The next event is:", next_general_event, show_cat=True)
if cloud_event != []:
    print_menu_section("The next cloud event is:", cloud_event)
if linux_event != []:
    print_menu_section("The next Linux event is:", linux_event)
if contains_collegues(bdays):
    print_bdays("The next birthdays are:", bdays, 2)
print "View all events | href=%s" % parser.get_events_overview_url()
print "---"
print "Visit Intranet | href=%s" % parser.get_base_url()
print "Visit Webmail | href=http://webmail.sioux.eu"
print "---"
print "Force refresh (current interval: %s) | size=8 refresh=true" % sys.argv[0].split('.')[1]
