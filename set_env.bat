@echo off
REM Set environment variables for local development

echo Setting up environment for Lemma Enterprise...

REM Core settings
set LEMMA_ADMIN_USER=admin
set LEMMA_ADMIN_PASS=password
set LEMMA_SECRET_KEY=dev_secret_key_change_in_production
set LEMMA_API_KEY=dev_api_key_change_in_production

REM Flask settings
set FLASK_APP=app.py
set FLASK_ENV=development

echo Environment variables set up successfully!
echo .
echo You can now run the application with 'python app.py'
