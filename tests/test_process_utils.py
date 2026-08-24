import io
import unittest

from process_utils import iter_decoded_chunks


class ShortReadStream(io.BytesIO):
    def read1(self, size=-1):
        return super().read(min(size, 2))


class ProcessUtilsTests(unittest.TestCase):
    def test_incremental_utf8_decoder_handles_split_characters(self):
        stream = ShortReadStream("进度 42% 完成".encode("utf-8"))
        self.assertEqual("".join(iter_decoded_chunks(stream)), "进度 42% 完成")


if __name__ == "__main__":
    unittest.main()
