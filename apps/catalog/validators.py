from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat
from PIL import Image, UnidentifiedImageError


def validate_product_image(file):
    """Reject oversized files and anything that is not a real JPEG/PNG/WebP image."""
    max_bytes = settings.PRODUCT_IMAGE_MAX_BYTES
    if file.size > max_bytes:
        raise ValidationError(
            f"“{file.name}” is {filesizeformat(file.size)}. The maximum size is {filesizeformat(max_bytes)}."
        )
    position = file.tell() if hasattr(file, "tell") else None
    try:
        with Image.open(file) as img:
            image_format = img.format
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValidationError(f"“{file.name}” is not a valid image.") from exc
    finally:
        if position is not None:
            file.seek(position)
    if image_format not in settings.PRODUCT_IMAGE_ALLOWED_FORMATS:
        raise ValidationError(f"“{file.name}” must be a JPEG, PNG or WebP image.")
