# Reality MCP Server

This is the Reality MCP Server for REVERIE, providing real-time data grounding like weather and news via MCP over streamable HTTP.

## Deployment

Deploy to Google Cloud Run using the following command:

```bash
gcloud run deploy reality-mcp --source . --allow-unauthenticated --port 8080
```
