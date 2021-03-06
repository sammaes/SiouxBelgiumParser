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
  - boto3
#### Possible issues:
##### MacOS
Following error can occur during installation of PIP packages: ‘could not uninstall <package_name>’.<br />
This can be resolved by running 'easy_install -U <package_name>' first.<br />
(reason: macOS SIP)<br />
Thanks to: https://github.com/Kevin-De-Koninck

### locale
Because this website is written in dutch it is required to have <b>nl_BE</b> enabled.

### .netrc
For authentication to the website add following to your .netrc file:
```
machine siouxehv.nl
login <sioux_username>
password <sioux_password>
```
Machine entry can also be changed if you pass it as an argument to the authenticate method.

### config.ini
You also need a configuration file which I can not publish on github (company sensitive data). <br />
This file can be obtained by sending an email to: <br />
<img src="https://github.com/sammaes/SiouxBelgiumParser/blob/master/Readme_resources/adres.png?raw=true" style="vertical-align: middle;" /><br />
Version compatible with current module: 02/12/2017.

## Documentation
The SiouxParser module documentation is generated by pdoc and can found at the following link:
<a href="https://sammaes.github.io/SiouxBelgiumParser/SiouxParser.html">pdoc documentation</a>

## Usecases

### BitBar Plugin
The Sioux Parser can be used in a [BitBar](https://github.com/matryer/bitbar) plugin as seen in the following screenshot:
<img src="https://github.com/sammaes/SiouxBelgiumParser/blob/master/Readme_resources/bitbar.png?raw=true" style="vertical-align: middle;" />

To enable this plugin, copy the content of the 'BitBar-Plugin' folder to the root of your BitBar-plugin folder. Next copy the file 'SiouxParser.py' to the folder 'scripts' that you just have copied to your BitBar-plugin folder.  
The last thing that you have to do is to copy your 'config.ini' file to this 'scripts' folder. If you rather keep a centralised version of the 'config.ini' file, than you can just edit line 13 of the BitBar plugin.
