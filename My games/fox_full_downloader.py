#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
野狐围棋 - 按用户 UID 全量下载棋谱

用法:
    python3 fox_full_downloader.py <uid> [输出目录]
    例如: python3 fox_full_downloader.py 531169471 ./my_kifu

接口:
    1) 列表: GET https://h5.foxwq.com/yehuDiamond/chessbook_local/YHWQFetchChessList
              ?uid=<uid>&type=4&lastcode=<lastcode>
       返回 {"result":0, "chesslist":[{...}, ...], ...}
       分页: 用上一页最后一条的 chessid 当 lastcode 拉下一页

    2) 棋谱: GET https://h5.foxwq.com/yehuDiamond/chessbook_local/YHWQFetchChess?chessid=<id>
       返回 {"result":0, "chess":"(;GM[1]...", ...}
"""

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API_LIST = "https://h5.foxwq.com/yehuDiamond/chessbook_local/YHWQFetchChessList"
API_CHESS = "https://h5.foxwq.com/yehuDiamond/chessbook_local/YHWQFetchChess"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Referer": "https://h5.foxwq.com/yehunewshare/",
    "Accept": "*/*",
}


def http_get_json(url, max_retries=3, timeout=30):
    last_err = None
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"请求失败 (重试 {max_retries} 次): {last_err}")


def fetch_chess_list(uid, lastcode=0, type_=4):
    """拉一页对局列表"""
    url = f"{API_LIST}?uid={uid}&type={type_}&lastcode={lastcode}"
    return http_get_json(url)


def fetch_all_games(uid, type_=4, max_pages=200):
    """
    分页拉取该用户的所有对局信息.
    返回 list of dict (每条对局的完整元信息).
    """
    all_games = []
    lastcode = 0
    seen_ids = set()

    for page in range(1, max_pages + 1):
        payload = fetch_chess_list(uid, lastcode=lastcode, type_=type_)
        chesslist = payload.get("chesslist", [])
        if not chesslist:
            print(f"  第 {page} 页: 空, 结束")
            break

        new_count = 0
        for g in chesslist:
            cid = g.get("chessid")
            if not cid or cid in seen_ids:
                continue
            seen_ids.add(cid)
            all_games.append(g)
            new_count += 1

        print(f"  第 {page} 页: {len(chesslist)} 条, 新增 {new_count} 条, 累计 {len(all_games)} 条")

        if new_count == 0:
            print("  无新增, 停止分页")
            break

        # 用最后一条 chessid 当 lastcode 翻页
        lastcode = chesslist[-1].get("chessid", 0)
        time.sleep(0.3)

    return all_games


def fetch_sgf(chessid):
    url = f"{API_CHESS}?chessid={chessid}"
    payload = http_get_json(url)
    if payload.get("result") != 0:
        raise RuntimeError(f"接口返回错误: {payload}")
    sgf = payload.get("chess", "")
    if not sgf:
        raise RuntimeError(f"SGF 为空: {payload}")
    return sgf


INVALID_CHARS = re.compile(r'[\\/:*?"<>|\s]')


def safe(s, maxlen=40):
    s = INVALID_CHARS.sub("_", str(s))
    return s[:maxlen].strip("._") or "_"


def make_filename(game):
    """
    生成可读的文件名:
    {starttime}_{black}[{blackdan}段]_VS_{white}[{whitedan}段]_{chessid}.sgf
    """
    starttime = game.get("starttime", "").split(" ")[0].replace("-", "") or "nodate"
    black = safe(game.get("blackenname", "?"))
    white = safe(game.get("whiteenname", "?"))
    bdan = game.get("blackdan", "")
    wdan = game.get("whitedan", "")
    cid = game.get("chessid", "")
    return f"{starttime}_{black}[{bdan}]_VS_{white}[{wdan}]_{cid}.sgf"


def main():
    if len(sys.argv) < 2:
        print("用法: python3 fox_full_downloader.py <uid> [输出目录]")
        print("例: python3 fox_full_downloader.py 531169471 ./my_kifu")
        sys.exit(1)

    uid = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) >= 3 else "./sgf"
    os.makedirs(output_dir, exist_ok=True)

    # 1. 拉对局列表
    print(f"=== 步骤 1: 拉取 uid={uid} 的全部对局列表 ===")
    games = fetch_all_games(uid)
    print(f"\n✓ 共找到 {len(games)} 局对局\n")

    if not games:
        print("没有对局, 退出")
        return

    # 2. 保存对局元信息为 CSV (方便你查阅)
    csv_path = os.path.join(output_dir, "_games_meta.csv")
    meta_fields = [
        "chessid", "starttime", "endtime",
        "blackenname", "blackdan", "whiteenname", "whitedan",
        "boardsize", "komi", "winner", "point", "reason", "movenum",
    ]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=meta_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(games)
    print(f"✓ 对局元信息已保存: {csv_path}")

    # 3. 下载每盘的 SGF
    print(f"\n=== 步骤 2: 下载 SGF 到 {output_dir}/ ===")
    success, skipped, failed = 0, 0, []

    for i, game in enumerate(games, 1):
        cid = game["chessid"]
        fn = make_filename(game)
        out_path = os.path.join(output_dir, fn)

        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            print(f"[{i}/{len(games)}] ⊘ 跳过: {fn}")
            skipped += 1
            continue

        try:
            sgf = fetch_sgf(cid)
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(sgf)
            print(f"[{i}/{len(games)}] ✓ {fn}  ({len(sgf)} chars)")
            success += 1
        except Exception as e:
            print(f"[{i}/{len(games)}] ✗ {cid}: {e}")
            failed.append((cid, str(e)))

        time.sleep(0.5)

    # 4. 汇总
    print(f"\n{'='*50}")
    print(f"完成: 成功 {success}, 跳过 {skipped}, 失败 {len(failed)}")
    if failed:
        with open(os.path.join(output_dir, "_failed.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["chessid", "error"])
            w.writerows(failed)
        print(f"失败记录: {os.path.join(output_dir, '_failed.csv')}")


if __name__ == "__main__":
    main()
