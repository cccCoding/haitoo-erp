import unittest

from pydantic import ValidationError

from app.schemas import ImageUploadPresignInput, MaterialUploadPresignInput, UploadPresignInput


class UploadLimitTests(unittest.TestCase):
    def test_creative_and_material_images_are_limited_to_three_megabytes(self):
        maximum = 3 * 1024 * 1024
        image = {"content_type": "image/png", "content_length": maximum}

        self.assertEqual(UploadPresignInput(**image).content_length, maximum)
        self.assertEqual(MaterialUploadPresignInput(files=[image]).files[0].content_length, maximum)

        oversized = {**image, "content_length": maximum + 1}
        with self.assertRaises(ValidationError):
            UploadPresignInput(**oversized)
        with self.assertRaises(ValidationError):
            MaterialUploadPresignInput(files=[oversized])

    def test_template_and_white_images_are_limited_to_three_megabytes(self):
        maximum = 3 * 1024 * 1024
        image = {"content_type": "image/png", "content_length": maximum}

        for category in ("template", "template-size-chart", "template-white"):
            with self.subTest(category=category):
                self.assertEqual(ImageUploadPresignInput(category=category, files=[image]).files[0].content_length, maximum)
                with self.assertRaises(ValidationError):
                    ImageUploadPresignInput(category=category, files=[{**image, "content_length": maximum + 1}])
