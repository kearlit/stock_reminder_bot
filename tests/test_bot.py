from datetime import datetime, date

import pytest
from unittest.mock import call

import pytz

from src import bot
from src.models import Mention, Reminder
from freezegun import freeze_time


class TestBot:
    @pytest.mark.usefixtures("mock_new_mention", "mock_alpha_vantage_get_intra_day")
    def test_saves_new_mentions(self, mock_tweepy):
        assert Mention.select().count() == 0

        bot.reply_to_mentions()

        mock_tweepy.assert_has_calls([call().mentions_timeline(since_id=None)])
        assert Mention.select().count() == 1

    @pytest.mark.usefixtures("mock_new_mention", "mock_alpha_vantage_get_intra_day")
    def test_creates_reminder_when_new_mention_contains_stock_and_date(self):
        assert Reminder.select().count() == 0

        with freeze_time("2020-12-13"):
            bot.reply_to_mentions()

        assert Reminder.select().count() == 1

        reminder = Reminder.select().first()
        assert reminder.tweet_id == 1
        assert reminder.created_on == date(2020, 12, 13)
        assert reminder.remind_on == "2021-03-13 01:00:00+00:00"
        assert reminder.stock_symbol == "AMZN"
        assert reminder.stock_price == 3112.70

    @pytest.mark.usefixtures("mock_new_mention", "mock_alpha_vantage_get_intra_day")
    def test_replies_to_new_mention_when_reminder_created(self, mock_tweepy):
        with freeze_time("2020-12-13"):
            bot.reply_to_mentions()

        expected_status_call = call().update_status(
            status="@user_name Sure thing buddy! I'll remind you of the price of "
            "$AMZN on 2021-03-13. I hope you make tons of money! 🤑",
            in_reply_to_status_id=1,
        )

        assert Reminder.select().count() == 1
        assert expected_status_call in mock_tweepy.mock_calls

    @pytest.mark.usefixtures("mention", "mock_alpha_vantage_get_intra_day")
    def test_replies_to_old_mention_when_reminder_date_is_today_and_stock_went_up(
            self, reminder, mock_tweepy
    ):
        with freeze_time(reminder.remind_on):
            bot.reply_to_reminders()

        expected_status_call = call().update_status(
            status="@user_name 3 months ago you bought $AMZN at $2954.91. It is now worth"
                   " $3112.70. That's a return of 5.34%! 🚀🤑📈",
            in_reply_to_status_id=1,
        )

        assert expected_status_call in mock_tweepy.mock_calls

    @pytest.mark.usefixtures("mention", "mock_alpha_vantage_get_intra_day")
    def test_replies_to_old_mention_when_reminder_date_is_today_and_stock_went_down(
            self, reminder, mock_tweepy
    ):
        reminder.stock_price = 3386.12
        reminder.save()
        with freeze_time(reminder.remind_on):
            bot.reply_to_reminders()

        expected_status_call = call().update_status(
            status="@user_name 3 months ago you bought $AMZN at $3386.12. It is now worth"
                   " $3112.70. That's a return of -8.07%! 😭📉",
            in_reply_to_status_id=1,
        )

        assert expected_status_call in mock_tweepy.mock_calls

    @pytest.mark.usefixtures("mention")
    def test_does_not_reply_to_old_mention_when_reminder_date_is_not_today(self, reminder, mock_tweepy):
        with freeze_time("2020-12-14"):
            bot.reply_to_reminders()

        mock_tweepy.assert_not_called()


class TestParseTweet:
    def test_returns_true_when_tweet_contains_cash_tag(self):

        assert bot.contains_stock("What is the price of $AMZN?") is True

    def test_returns_false_when_tweet_does_not_contain_cash_tag(self):

        assert bot.contains_stock("What is the price of amazon?") is False

    def test_returns_true_when_tweet_contains_date(self):

        assert bot.contains_date("Remind me of $AMZN in one year") is True

    def test_returns_false_when_tweet_does_not_contain_date(self):

        assert bot.contains_date("Hello there!") is False

    @pytest.mark.parametrize(
        "tweet, stock_name",
        [
            ("What is the price of $AMZN?", "AMZN"),
            ("How much is $WMT right now?", "WMT"),
        ],
    )
    def test_returns_stock_name_when_tweet_contains_cash_tag(self, tweet, stock_name):
        assert bot.parse_stock_symbol(tweet) == stock_name

    @pytest.mark.usefixtures("mock_alpha_vantage_get_intra_day")
    def test_returns_stock_price_with_two_decimal_places(self):
        price = bot.get_price("AMZN")

        assert price == 3112.70

    @pytest.mark.parametrize(
        "string, reminder_date",
        [
            ("in 3 days", datetime(2020, 12, 16, 11, tzinfo=pytz.utc)),
            ("in one week", datetime(2020, 12, 20, 11, tzinfo=pytz.utc)),
            ("in two months", datetime(2021, 2, 13, 11, tzinfo=pytz.utc)),
            ("in 2 years", datetime(2022, 12, 13, 11, tzinfo=pytz.utc)),
        ],
    )
    def test_calculates_reminder_date_from_string(self, string, reminder_date):
        with freeze_time("2020-12-13"):
            assert bot.calculate_reminder_date(string).date() == reminder_date.date()
