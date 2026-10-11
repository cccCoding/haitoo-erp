from threading import Lock
from time import sleep
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError, ReadTimeoutError

from app import creative_resource_sizes as sizes


class CreativeResourceSizeTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.client.head_object.return_value = {"ContentLength": 2048}
        self.settings = SimpleNamespace(
            r2_endpoint="https://r2.invalid", r2_account_id=None, r2_access_key_id="access",
            r2_secret_access_key="secret", r2_bucket="images", r2_public_base_url="https://cdn.invalid",
        )
        sizes._cache.clear()
        for target, value in (("get_settings", self.settings), ("_metadata_client", self.client)):
            mock = patch.object(sizes, target, return_value=value)
            mock.start(); self.addCleanup(mock.stop)

    def images(self, *names):
        return [(index+1, f"https://cdn.invalid/template-white/company/1/{name}.png")
                for index, name in enumerate(names)]

    def test_success_duplicate_cache_zero_size_and_changed_object(self):
        result = sizes.read_white_image_sizes(1, self.images('a', 'a'))
        self.assertEqual([item['size_bytes'] for item in result], [2048, 2048])
        self.client.head_object.assert_called_once_with(Bucket='images', Key='template-white/company/1/a.png')
        sizes.read_white_image_sizes(1, self.images('a'))
        self.assertEqual(self.client.head_object.call_count, 1)
        self.client.head_object.return_value = {"ContentLength": 0}
        self.assertEqual(sizes.read_white_image_sizes(1, self.images('b'))[0]['size_bytes'], 0)
        self.assertEqual(self.client.head_object.call_count, 2)

    def test_cache_expiry_and_capacity(self):
        with patch.object(sizes, 'monotonic', return_value=100):
            sizes.read_white_image_sizes(1, self.images('a'))
        with patch.object(sizes, 'monotonic', return_value=100+sizes.CACHE_TTL_SECONDS):
            sizes.read_white_image_sizes(1, self.images('a'))
        self.assertEqual(self.client.head_object.call_count, 2)
        with patch.object(sizes, 'CACHE_CAPACITY', 2):
            sizes.read_white_image_sizes(1, self.images('b', 'c'))
        self.assertEqual(len(sizes._cache), 2)
        self.assertNotIn(('https://r2.invalid', 'images', 'template-white/company/1/a.png'), sizes._cache)

    def test_invalid_urls_never_reach_r2(self):
        urls = [
            'https://evil.invalid/a.png',
            'https://cdn.invalid.evil.invalid/template-white/company/1/a.png',
            'https://cdn.invalid/template-white/company/2/a.png',
            'https://cdn.invalid/generated/company/1/a.png',
            'https://cdn.invalid/template-white/company/1/../a.png',
            'https://cdn.invalid/template-white/company/1/%2e%2e/a.png',
        ]
        result = sizes.read_white_image_sizes(1, list(enumerate(urls, 1)))
        self.assertTrue(all(item['status'] == 'invalid_url' and item['size_bytes'] is None for item in result))
        self.client.head_object.assert_not_called()

    def test_missing_timeout_and_config_failure_are_retryable(self):
        self.client.head_object.side_effect = ClientError({'Error': {'Code': 'NoSuchKey'}}, 'HeadObject')
        self.assertEqual(sizes.read_white_image_sizes(1, self.images('a'))[0]['status'], 'not_found')
        self.client.head_object.side_effect = ReadTimeoutError(endpoint_url='https://r2.invalid')
        self.assertEqual(sizes.read_white_image_sizes(1, self.images('a'))[0]['status'], 'unavailable')
        self.assertEqual(len(sizes._cache), 0)
        self.client.head_object.side_effect = None
        self.assertEqual(sizes.read_white_image_sizes(1, self.images('a'))[0]['size_bytes'], 2048)
        self.settings.r2_access_key_id = None
        self.assertEqual(sizes.read_white_image_sizes(1, self.images('b'))[0]['status'], 'unavailable')

    def test_reads_are_limited_to_four_concurrent_objects(self):
        lock = Lock()
        active = 0
        peak = 0

        def read(**kwargs):
            nonlocal active, peak
            with lock:
                active += 1; peak = max(peak, active)
            sleep(0.02)
            with lock:
                active -= 1
            return {'ContentLength': 100}

        self.client.head_object.side_effect = read
        result = sizes.read_white_image_sizes(1, self.images(*(str(index) for index in range(20))))
        self.assertTrue(all(item['status'] == 'available' for item in result))
        self.assertGreater(peak, 1)
        self.assertLessEqual(peak, 4)

    def test_metadata_client_uses_short_timeouts_without_retries(self):
        # 使用真实工厂检查专用客户端配置，不执行网络请求。
        with patch.object(sizes.boto3, 'client', return_value=Mock()) as create:
            self._metadata_factory.__wrapped__('https://r2.invalid', 'access', 'secret')
        config = create.call_args.kwargs['config']
        self.assertEqual((config.connect_timeout, config.read_timeout), (2, 3))
        self.assertEqual(config.retries['total_max_attempts'], 1)

    _metadata_factory = staticmethod(sizes._metadata_client)


if __name__ == '__main__':
    unittest.main()
