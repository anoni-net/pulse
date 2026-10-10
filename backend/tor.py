"""Fetch tor metrics

https://metrics.torproject.org/onionoo.html

"""

import logging
import sys

import click

from countries import COUNTRIES
from pgdb import PGConn
from tor_onionoo import TorOnionoo

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(stream=sys.stdout),
    ],
)

logger = logging.getLogger("tor-details")


@click.group()
def cli():
    """cli for groups"""


def fetch_and_save(country: str, save: bool = True) -> bool:
    """收集一個國家的一份快照，成功回傳 True。"""
    try:
        resp_details = TorOnionoo().get_details(country=country)
    except Exception as e:
        logger.error("Failed to fetch Onionoo data for %s: %s", country, e)
        return False

    bandwidth = 0
    for relay in resp_details.relays:
        bandwidth += relay.observed_bandwidth or 0
        logger.info(relay)

    logger.info(
        f"bandwidth: {bandwidth / 1000 / 1000:.4f} MB/s ({bandwidth / 1000 / 1000 * 8:.4f} Mb/s)"
    )
    logger.info(f"relays: {len(resp_details.relays)}")

    if save:
        sql = """INSERT INTO relay_details (
                       created_at,
                       fingerprint,
                       nickname,
                       running,
                       measured,
                       asn,
                       as_name,
                       consensus_weight,
                       platform,
                       version,
                       country,
                       country_name,
                       contact,
                       flags,
                       first_seen,
                       last_seen,
                       last_changed,
                       bandwidth_rate,
                       bandwidth_burst,
                       observed_bandwidth,
                       advertised_bandwidth,
                       consensus_weight_fraction,
                       guard_probability,
                       middle_probability,
                       exit_probability
                    ) VALUES (
                       %(created_at)s,
                       %(fingerprint)s,
                       %(nickname)s,
                       %(running)s,
                       %(measured)s,
                       %(asn)s,
                       %(as_name)s,
                       %(consensus_weight)s,
                       %(platform)s,
                       %(version)s,
                       %(country)s,
                       %(country_name)s,
                       %(contact)s,
                       %(flags)s,
                       %(first_seen)s,
                       %(last_seen)s,
                       %(last_changed)s,
                       %(bandwidth_rate)s,
                       %(bandwidth_burst)s,
                       %(observed_bandwidth)s,
                       %(advertised_bandwidth)s,
                       %(consensus_weight_fraction)s,
                       %(guard_probability)s,
                       %(middle_probability)s,
                       %(exit_probability)s
                       )
                ON CONFLICT (created_at, fingerprint) DO NOTHING
            """
        logger.info("Going into connecting DB")
        with PGConn() as pg:
            for relay in resp_details.relays:
                relay_dict = relay.model_dump()
                relay_dict["created_at"] = resp_details.relays_published
                logger.info(relay_dict)
                pg.cur.execute(sql, relay_dict)
    return True


@cli.command("details", short_help="Get tor nodes details")
@click.option("--country", default="tw", help="country code")
@click.option("--save", default=True, help="save to the database")
def details(country="tw", save=True):
    """收集單一國家"""
    if not fetch_and_save(country, save):
        raise SystemExit(1)


@cli.command("collect", short_help="Collect every country in countries.py")
@click.option("--save", default=True, help="save to the database")
def collect(save=True):
    """依序收集 countries.py 的所有國家。

    一次一個，不同時打 Onionoo。某個國家失敗不影響其他國家，全部跑完才以 1 結束。
    """
    failed = []
    for country in COUNTRIES:
        try:
            ok = fetch_and_save(country, save)
        except Exception:
            logger.exception("Failed to save %s", country)
            ok = False
        if not ok:
            failed.append(country)
    if failed:
        logger.error("collect failed for: %s", ", ".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    cli()
