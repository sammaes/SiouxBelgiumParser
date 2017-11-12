# Sioux Belgium Parser
Python script to parse the Sioux Belgium intranet website.
This script is only meant for Sioux Belgium employees.

## Requirements

### Packages
- python (2.7)
- pip
- pip packages:
  - requests
  - requests_ntlm
  - beautifulsoup4
  - pyopenssl

### .netrc
For authentication to the website add following to your .netrc file:
```
machine siouxehv.nl
login <sioux_username>
password <sioux_password>
```
Machine entry can also be changed if you pass it as an argument to the authenticate method.

### config.ini
You also need a configuration file which I can not publish on github (company sensitive data).
This file can be obtained by sending an email to <img src="https://github.com/sammaes/SiouxBelgiumParser/blob/master/Readme_resources/adres.png?raw=true" />
