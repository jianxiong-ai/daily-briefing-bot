import unittest

from daily_briefing.push import (
    PushResult,
    build_feishu_card_payload,
    build_wechat_content,
    truncate_utf8_plain,
    wechat_work_markdown,
)


class PushTests(unittest.TestCase):
    def test_build_feishu_card_payload(self):
        payload = build_feishu_card_payload("日报", [["A"], ["B", "C"]])
        self.assertEqual(payload["msg_type"], "interactive")
        self.assertEqual(payload["card"]["header"]["title"]["content"], "日报")
        self.assertEqual(payload["card"]["elements"][0]["content"], "A")
        self.assertEqual(payload["card"]["elements"][1]["tag"], "hr")

    def test_wechat_markdown_strips_feishu_markup(self):
        text = wechat_work_markdown("<font color='blue'>标题</font> [链接](https://example.com)")
        self.assertEqual(text, "标题 链接")

    def test_build_wechat_content_skips_prefix_and_truncates(self):
        content = build_wechat_content(
            "标题",
            [["原文： 1 2 3", "**正文** " + "长" * 2000]],
            max_bytes=120,
            skip_prefixes=("原文",),
        )
        self.assertTrue(content.startswith("**标题**\n正文"))
        self.assertIn("其余内容见飞书完整版", content)
        self.assertNotIn("原文", content)

    def test_truncate_utf8_plain_keeps_valid_text(self):
        self.assertEqual(truncate_utf8_plain("abc", 10), "abc")
        self.assertTrue(truncate_utf8_plain("中文中文中文", 8).endswith("..."))

    def test_push_result_raises_with_errors_when_nothing_sent(self):
        result = PushResult()
        result.add_error("feishu", "主机器人", "failed")
        with self.assertRaises(RuntimeError) as raised:
            result.raise_if_empty(["image: failed"])
        self.assertIn("feishu/主机器人", str(raised.exception))
        self.assertIn("image: failed", str(raised.exception))

        result.add_success()
        result.raise_if_empty()


if __name__ == "__main__":
    unittest.main()
