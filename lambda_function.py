import io
import logging
import os
from pathlib import PurePosixPath

import boto3
from PIL import Image, ImageOps, UnidentifiedImageError

s3 = boto3.client("s3")
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


def make_thumbnail(data):
    with Image.open(io.BytesIO(data), formats=["JPEG", "PNG"]) as source:
        if source.width * source.height > 25_000_000:
            raise ValueError("Image exceeds 25 million pixels")
        image = ImageOps.exif_transpose(source).convert("RGBA")
        image.thumbnail((256, 256), Image.Resampling.LANCZOS)
        result = io.BytesIO()
        image.save(result, format="PNG")
        return result.getvalue()


def lambda_handler(event, context):
    # API requests supply key directly; S3 uploads arrive through EventBridge.
    key = event.get("key") or event.get("detail", {}).get("object", {}).get("key")
    if not isinstance(key, str) or PurePosixPath(key).suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        return {"ok": False, "reason": "Supply the key of a JPG or PNG image."}

    response = s3.get_object(Bucket=os.environ["ORIGINALS_BUCKET"], Key=key)
    with response["Body"] as stream:
        if response["ContentLength"] > 10 * 1024 * 1024:
            return {"ok": False, "reason": "Image exceeds 10 MiB."}
        try:
            thumbnail = make_thumbnail(stream.read())
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            return {"ok": False, "reason": "Cannot resize this image."}

    output_key = f"thumbnails/{key}.png"
    s3.put_object(Bucket=os.environ["THUMBNAILS_BUCKET"], Key=output_key,
                  Body=thumbnail, ContentType="image/png")
    log.info("Saved %s", output_key)
    return {"ok": True, "key": output_key}
