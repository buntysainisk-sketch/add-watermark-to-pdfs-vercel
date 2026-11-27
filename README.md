# Taxmann PDF Watermark Tool - Vercel

This folder is a self-contained Vercel deployment copy of the Taxmann PDF Watermark Tool.

## Deploy

1. Create a GitHub repository containing the contents of this `vercel` directory.
2. In Vercel, click **Add New → Project**.
3. Import the GitHub repository.
4. Deploy with the default settings.

Vercel detects `vercel.json`, installs `requirements.txt`, and uses `api/index.py` as the Python serverless function.

## Important Vercel limits

The Vercel version accepts PDFs up to 4 MB because Vercel serverless functions have request-body limits. The generated PDF is returned directly to the browser, so it does not depend on persistent server storage between requests.
