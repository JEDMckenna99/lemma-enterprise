# Lemma Enterprise Deployment Guide

This guide provides step-by-step instructions for deploying the Lemma Human Verification System to Azure.

## Prerequisites

- Azure account with subscription
- Azure CLI installed and configured
- Git (optional)

## Deployment Options

### Option 1: Azure App Service (Recommended)

1. **Prepare your deployment package**:
   ```bash
   # Zip the contents of the lemma-enterprise-package directory
   cd lemma-enterprise-package
   zip -r ../lemma-enterprise.zip *
   ```

2. **Create a resource group** (if you don't already have one):
   ```bash
   az group create --name LemmaResourceGroup --location eastus
   ```

3. **Create an App Service plan**:
   ```bash
   az appservice plan create --name LemmaPlan --resource-group LemmaResourceGroup --sku B1
   ```

4. **Create a web app**:
   ```bash
   az webapp create --name LemmaHumanVerification --resource-group LemmaResourceGroup --plan LemmaPlan --runtime "PYTHON:3.9"
   ```

5. **Configure environment variables**:
   ```bash
   az webapp config appsettings set --resource-group LemmaResourceGroup --name LemmaHumanVerification --settings LEMMA_ADMIN_USER="your_admin_username" LEMMA_ADMIN_PASS="your_secure_password" LEMMA_SECRET_KEY="your_random_secret"
   ```

6. **Deploy your code**:
   ```bash
   az webapp deployment source config-zip --resource-group LemmaResourceGroup --name LemmaHumanVerification --src ../lemma-enterprise.zip
   ```

7. **Access your application**:
   ```
   https://lemmahumanverification.azurewebsites.net
   ```

### Option 2: Azure Container Instances

1. **Create a Dockerfile**:
   ```
   FROM python:3.9-slim

   WORKDIR /app

   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt

   COPY . .

   EXPOSE 5000

   CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
   ```

2. **Build and push the Docker image**:
   ```bash
   az acr build --registry YourRegistry --image lemma-enterprise:latest .
   ```

3. **Deploy to Azure Container Instances**:
   ```bash
   az container create --resource-group LemmaResourceGroup --name lemma-enterprise --image YourRegistry.azurecr.io/lemma-enterprise:latest --dns-name-label lemma-enterprise --ports 5000 --environment-variables LEMMA_ADMIN_USER="your_admin_username" LEMMA_ADMIN_PASS="your_secure_password" LEMMA_SECRET_KEY="your_random_secret"
   ```

## Post-Deployment Steps

1. **Set up custom domain** (optional):
   ```bash
   az webapp config hostname add --webapp-name LemmaHumanVerification --resource-group LemmaResourceGroup --hostname yourdomain.com
   ```

2. **Enable HTTPS**:
   - For App Service, HTTPS is enabled by default
   - For custom domains, configure SSL binding in the Azure Portal

3. **Configure scaling** (for production):
   ```bash
   az appservice plan update --name LemmaPlan --resource-group LemmaResourceGroup --sku S1
   ```

## Monitoring and Maintenance

1. **View logs**:
   ```bash
   az webapp log tail --name LemmaHumanVerification --resource-group LemmaResourceGroup
   ```

2. **Set up Application Insights** (optional):
   ```bash
   az monitor app-insights component create --app LemmaInsights --location eastus --resource-group LemmaResourceGroup
   ```

3. **Configure alerts** (recommended for production):
   ```bash
   az monitor metrics alert create --name "HighCPU" --resource-group LemmaResourceGroup --scopes $(az webapp show --name LemmaHumanVerification --resource-group LemmaResourceGroup --query id -o tsv) --condition "avg Percentage CPU > 80" --window-size 5m --evaluation-frequency 1m
   ```

## Backup and Disaster Recovery

For production deployments, ensure you regularly back up the `.lemma_enterprise` directory which contains your cryptographic keys and credential registry.

## Security Best Practices

1. **Rotate admin credentials** periodically
2. **Use a strong, randomly generated secret key**
3. **Implement IP restrictions** for admin access
4. **Enable Azure Security Center** for threat detection
5. **Review access logs** regularly

## Troubleshooting

If you encounter issues with your deployment:

1. Check application logs in the Azure Portal
2. Verify environment variables are set correctly
3. Ensure the `.lemma_enterprise` directory is writable
4. Check for any network restrictions or firewall rules
