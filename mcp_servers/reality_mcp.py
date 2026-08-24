from mcp.server.fastmcp import FastMCP
import httpx
import asyncio

# Initialize FastMCP server
mcp = FastMCP("reality-mcp")

@mcp.tool()
async def get_current_weather(location: str = "Reverie Town") -> dict:
    """Gets the current weather for a location. Used by characters to plan their day."""
    # Returns a fixed weather state; swap in an Open-Meteo call for live data.
    weather_options = [
        {"condition": "rain", "temp": 55, "description": "Heavy rain, good for staying inside."},
        {"condition": "clear", "temp": 72, "description": "Clear skies, perfect for the park."},
        {"condition": "overcast", "temp": 65, "description": "Cloudy, neutral mood."}
    ]
    return weather_options[0]

@mcp.tool()
async def get_top_headlines(category: str = "local") -> list:
    """Gets top news headlines. Used by characters to spark conversation or motivation."""
    # Static headlines; replace with a live news API for dynamic narrative catalysts.
    return [
        "Local chef wins regional award, sparking jealousy in the culinary scene.",
        "Traffic jam on 5th Avenue delays the morning commute.",
        "Festival planning committee seeks volunteers for next week."
    ]

if __name__ == "__main__":
    # Run as a web server using SSE/Streamable HTTP transport
    mcp.run(transport="streamable-http", port=8080)
