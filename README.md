# Unifi Protect Timelapse
A simple python script that generates a daily timelapse with dynamic capture intervals when motion is detected.

## Installation (MacOS via Terminal)
Clone repository to desired location
```bash
git clone https://github.com/petykowski/unifi-protect-timelapse.git
```

## Getting Started
Create Python virtual environent and install dependencies
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Create a Long-Lived Access Token
To talk to the API, you need an "identity card" for your script.
1. Log in to your Home Assistant UI.
2. Click on your Profile (your name/icon in the bottom left).
3. Scroll all the way to the bottom to Long-Lived Access Tokens.
4. Click Create Token, give it a name (e.g., "Python Script"), and copy the long string.

**_Warning: You will only see this string once. Save it in a secure place._**

### Create and Config.py File
Create a copy of the config_sample.py file
```bash
cp config_sample.py config.py
```
Replace dummy values with local values
```bash
camera_url = 'http://ip_address_to_camera'

output_path_full_resolution = ('~/', 'Desktop', 'Example')
output_path_home_assistant = ('/Volumes', 'External Drive', 'Timelapse', 'Example')

ha_url = 'https://url_to_home_assistant.com/'
ha_url_websocket = 'wss://url_to_home_assistant.com/api/websocket'
ha_long_lived_token = 'lOnGLIVedtoKeN'
ha_detection_entity_id = 'input_boolean.name_of_motion_detector'
```

## Start Timelapse

If virual environment is not already running
```bash
source .venv/bin/activate
```
Otherwise
```bash
python timelapse.py
```