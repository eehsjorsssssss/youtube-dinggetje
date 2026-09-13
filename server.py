import os
import hashlib
import tempfile
import requests
from fastmcp import FastMCP

mcp = FastMCP("Creatomate YouTube Bridge")

COMPOSIO_API_KEY = os.environ.get("COMPOSIO_API_KEY")
COMPOSIO_UPLOAD_URL = "https://backend.composio.dev/api/v3.1/files/upload/request"


@mcp.tool()
def stage_creatomate_video(
    video_url: str,
    filename: str = "video.mp4"
) -> dict:
    """
    Downloads a Creatomate-rendered MP4 and uploads it to
    Composio's file storage so it can be passed to YouTube.
    """

    if not COMPOSIO_API_KEY:
        raise RuntimeError("COMPOSIO_API_KEY is not configured.")

    if not video_url.startswith(("http://", "https://")):
        raise ValueError("video_url must start with http:// or https://")

    if not filename.endswith(".mp4"):
        filename += ".mp4"

    temp_path = None

    try:
        # Download the Creatomate video
        response = requests.get(
            video_url,
            stream=True,
            timeout=180
        )
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".mp4"
        ) as temp_file:
            temp_path = temp_file.name

            for chunk in response.iter_content(
                chunk_size=1024 * 1024
            ):
                if chunk:
                    temp_file.write(chunk)

        # Calculate MD5
        md5 = hashlib.md5()

        with open(temp_path, "rb") as video_file:
            while True:
                chunk = video_file.read(1024 * 1024)

                if not chunk:
                    break

                md5.update(chunk)

        md5_hex = md5.hexdigest()

        # Ask Composio for an upload URL
        headers = {
            "x-api-key": COMPOSIO_API_KEY,
            "Content-Type": "application/json"
        }

        payload = {
            "toolkit_slug": "youtube",
            "tool_slug": "YOUTUBE_MULTIPART_UPLOAD_VIDEO",
            "filename": filename,
            "mimetype": "video/mp4",
            "md5": md5_hex
        }

        upload_response = requests.post(
            COMPOSIO_UPLOAD_URL,
            headers=headers,
            json=payload,
            timeout=60
        )

        upload_response.raise_for_status()

        upload_data = upload_response.json()

        presigned_url = upload_data["new_presigned_url"]
        s3key = upload_data["key"]

        # Upload the actual MP4 to Composio
        with open(temp_path, "rb") as video_file:
            put_response = requests.put(
                presigned_url,
                data=video_file,
                headers={
                    "Content-Type": "video/mp4"
                },
                timeout=300
            )

        put_response.raise_for_status()

        # Return the file reference Composio's YouTube tool needs
        return {
            "name": filename,
            "mimetype": "video/mp4",
            "s3key": s3key
        }

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000))
    )
