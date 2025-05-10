@echo off
REM Set environment variables for Lemma Enterprise testing

REM Admin credentials
set LEMMA_ADMIN_USER=admin
set LEMMA_ADMIN_PASS=password
set LEMMA_SECRET_KEY=test-secret-key-for-development-only

REM Flask settings
set FLASK_DEBUG=True
set FLASK_APP=app.py

REM Uncomment and set these with your Twilio credentials to enable SMS
REM set TWILIO_ACCOUNT_SID=your_account_sid
REM set TWILIO_AUTH_TOKEN=your_auth_token
REM set TWILIO_PHONE_NUMBER=your_twilio_phone_number

echo Environment variables set for Lemma Enterprise testing
echo.
echo To enable SMS functionality, edit this file and add your Twilio credentials.
echo.
