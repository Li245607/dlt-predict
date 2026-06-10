# -*- coding: utf-8 -*-
"""大乐透预测 + 验证 + 学习 综合脚本"""
import urllib.request, urllib.parse, re, json, random, os, glob
from datetime import datetime
from collections import Counter

WORK_DIR = os.environ.get("GITHUB_WORKSPACE") or os.getcwd()
LEARN_DB = os.path.join(WORK_DIR, "dlt_learn.json")

def load_learn():
    if os.path.exists(LEARN_DB):
        with open(LEARN_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"history": [], "weights": {"hot_w": 0.4, "cold_w": 0.3},
            "total_possible": 0, "total_hits": 0, "best_hit": 0, "rounds": 0}

def save_learn(db):
    with open(LEARN_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def fetch_history(count=50):
    url = "https://datachart.500.com/dlt/history/newinc/history.php?start=26000&end=26999"
    r = urllib.request.urlopen(url, timeout=15)
    data = r.read().decode("utf-8", errors="replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", data, re.DOTALL)
    results = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        clean = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        if len(clean) >= 9 and clean[1].isdigit():
            front = [int(x) for x in clean[2:7] if x.isdigit()]
            back = [int(x) for x in clean[7:9] if x.isdigit()]
            if len(front) == 5 and len(back) == 2:
                results.append({"issue": clean[1], "front": front, "back": back, "date": clean[-1] if len(clean) > 9 else ""})
        if len(results) >= count:
            break
    return results

def analyze_cold_hot(history, hot_window=20, cold_threshold=10):
    recent_front = [n for draw in history[:hot_window] for n in draw["front"]]
    recent_back = [n for draw in history[:hot_window] for n in draw["back"]]
    front_freq = Counter(recent_front)
    back_freq = Counter(recent_back)
    front_last_seen = {}
    back_last_seen = {}
    total = len(history)
    for idx, draw in enumerate(history):
        for n in draw["front"]:
            if n not in front_last_seen:
                front_last_seen[n] = idx
        for n in draw["back"]:
            if n not in back_last_seen:
                back_last_seen[n] = idx
    front_hot = [n for n in range(1, 36) if front_freq.get(n, 0) >= 3]
    front_warm = [n for n in range(1, 36) if front_freq.get(n, 0) == 2]
    front_cold = [n for n in range(1, 36) if front_last_seen.get(n, total) >= cold_threshold and n not in front_hot]
    back_hot = [n for n in range(1, 13) if back_freq.get(n, 0) >= 2]
    back_warm = [n for n in range(1, 13) if back_freq.get(n, 0) == 1]
    back_cold = [n for n in range(1, 13) if back_last_seen.get(n, total) >= 8 and n not in back_hot]
    front_omission = {n: front_last_seen.get(n, total) for n in range(1, 36)}
    back_omission = {n: back_last_seen.get(n, total) for n in range(1, 13)}
    return {"front_hot": sorted(set(front_hot)), "front_warm": sorted(set(front_warm) - set(front_hot)),
            "front_cold": sorted(set(front_cold)), "back_hot": sorted(set(back_hot)),
            "back_warm": sorted(set(back_warm) - set(back_hot)), "back_cold": sorted(set(back_cold)),
            "front_omission": front_omission, "back_omission": back_omission}

def analyze_zones(history, count=20):
    zones = {"一区(1-12)": (1, 12), "二区(13-24)": (13, 24), "三区(25-35)": (25, 35)}
    recent = history[:count]
    return {name: len([n for draw in recent for n in draw["front"] if lo <= n <= hi])
            for name, (lo, hi) in zones.items()}

def analyze_odd_even(history, count=20):
    ratios = []
    for draw in history[:count]:
        odd = sum(1 for n in draw["front"] if n % 2 == 1)
        ratios.append(f"{odd}:{5-odd}")
    return Counter(ratios)

def analyze_back_zones(history, count=20):
    zones = {"一区(1-4)": (1, 4), "二区(5-8)": (5, 8), "三区(9-12)": (9, 12)}
    recent = history[:count]
    return {name: len([n for draw in recent for n in draw["back"] if lo <= n <= hi])
            for name, (lo, hi) in zones.items()}

def generate_predictions(history, cold_hot, count=5):
    front_hot, front_warm, front_cold = cold_hot["front_hot"], cold_hot["front_warm"], cold_hot["front_cold"]
    back_hot, back_warm, back_cold = cold_hot["back_hot"], cold_hot["back_warm"], cold_hot["back_cold"]
    weights = load_learn().get("weights", {"hot_w": 0.4, "cold_w": 0.3})
    hot_n = max(1, min(3, round(weights["hot_w"] * 5)))
    cold_n = max(0, min(2, round(weights["cold_w"] * 5)))
    warm_n = 5 - hot_n - cold_n
    predictions = []
    for _ in range(count * 4):
        temp = set()
        if front_hot and len(temp) < hot_n:
            temp.update(random.sample(front_hot, min(hot_n - len(temp), len(front_hot))))
        if front_warm:
            needed = min(warm_n, len(front_warm))
            temp.update(random.sample(front_warm, min(needed, len(front_warm))))
        if front_cold and len(temp) < 5:
            needed = min(cold_n, len(front_cold))
            temp.update(random.sample(front_cold, min(needed, len(front_cold))))
        if len(temp) < 5:
            extra = [n for n in range(1, 36) if n not in temp]
            temp.update(random.sample(extra, min(5 - len(temp), len(extra))))
        front = sorted(list(temp))[:5]
        odd_count = sum(1 for n in front if n % 2 == 1)
        for _ in range(15):
            if odd_count in (2, 3):
                break
            idx = random.randint(0, 4)
            if odd_count > 3 and front[idx] % 2 == 1:
                cand = [n for n in range(2, 36, 2) if n not in front]
                if cand:
                    front[idx] = random.choice(cand)
                    odd_count -= 1
            elif odd_count < 2 and front[idx] % 2 == 0:
                cand = [n for n in range(1, 36, 2) if n not in front]
                if cand:
                    front[idx] = random.choice(cand)
                    odd_count += 1
        if random.random() < 0.35:
            cand = [n for n in history[0]["front"] if n not in front]
            if cand:
                front[random.randint(0, 4)] = random.choice(cand)
        front = sorted(front)[:5]
        back_picks = []
        if back_hot:
            back_picks.append(random.choice(back_hot))
        if back_cold:
            back_picks.append(random.choice(back_cold))
        elif back_warm:
            back_picks.append(random.choice(back_warm))
        while len(back_picks) < 2:
            cand = [n for n in range(1, 13) if n not in back_picks]
            back_picks.append(random.choice(cand))
        back_odd = sum(1 for n in back_picks if n % 2 == 1)
        if back_odd == 0:
            cand = [n for n in range(1, 13, 2) if n not in back_picks]
            if cand:
                back_picks[random.randint(0, 1)] = random.choice(cand)
        elif back_odd == 2:
            cand = [n for n in range(2, 13, 2) if n not in back_picks]
            if cand:
                back_picks[random.randint(0, 1)] = random.choice(cand)
        back = sorted(back_picks[:2])
        front = sorted(front)[:5]
        if len(set(front)) == 5 and len(set(back)) == 2:
            key = str(front) + str(back)
            if key not in [str(p["front"]) + str(p["back"]) for p in predictions]:
                predictions.append({"front": front, "back": back})
        if len(predictions) >= count:
            break
    return predictions[:count]

def generate_report(history, ch, zs, oe, bz, predictions):
    lines = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines.append(f"# 大乐透预测报告")
    lines.append(f"")
    lines.append(f"生成时间: {now}")
    lines.append(f"数据源: 500.com (最近 {len(history)} 期)")
    lines.append("")
    latest = history[0]
    lines.append(f"## 最新开奖")
    lines.append(f"第 {latest['issue']} 期 ({latest['date']})")
    lines.append(f"前区: {'  '.join(f'{n:02d}' for n in latest['front'])}")
    lines.append(f"后区: {'  '.join(f'{n:02d}' for n in latest['back'])}")
    lines.append("")
    lines.append(f"## 冷热号分析 (近20期)")
    lines.append(f"热号: {', '.join(f'{n:02d}' for n in ch['front_hot']) or '无'}")
    lines.append(f"温号: {', '.join(f'{n:02d}' for n in ch['front_warm']) or '无'}")
    lines.append(f"冷号: {', '.join(f'{n:02d}' for n in ch['front_cold']) or '无'}")
    lines.append("")
    sorted_om = sorted(ch["front_omission"].items(), key=lambda x: -x[1])
    lines.append("### 遗漏值 TOP 10")
    for n, v in sorted_om[:10]:
        lines.append(f"- {n:02d}: 遗漏 {v} 期 {' <<<' if v >= 20 else ''}")
    lines.append("")
    lines.append("## 后区分析")
    lines.append(f"热号: {', '.join(f'{n:02d}' for n in ch['back_hot']) or '无'}")
    lines.append(f"温号: {', '.join(f'{n:02d}' for n in ch['back_warm']) or '无'}")
    lines.append(f"冷号: {', '.join(f'{n:02d}' for n in ch['back_cold']) or '无'}")
    lines.append("")
    lines.append("## 前区区间分布")
    for zone, c in sorted(zs.items()):
        bar = chr(9608) * min(c, 20) + chr(9617) * max(0, 20 - min(c, 20))
        lines.append(f"- {zone}: {c} 次 {bar}")
    lines.append("")
    total = sum(oe.values()) or 1
    lines.append("## 奇偶比统计")
    for ratio, c in oe.most_common(5):
        lines.append(f"- {ratio}: {c} 次 ({c/total*100:.0f}%)")
    lines.append("")
    lines.append("## 后区区间分布")
    for zone, c in sorted(bz.items()):
        bar = chr(9608) * min(c, 15) + chr(9617) * max(0, 15 - min(c, 15))
        lines.append(f"- {zone}: {c} 次 {bar}")
    lines.append("")
    lines.append("## 本期预测号码")
    for i, pred in enumerate(predictions, 1):
        tags = []
        for n in pred["front"]:
            if n in ch["front_hot"]:
                tags.append("[H]")
            elif n in ch["front_cold"]:
                tags.append("[C]")
            elif n in ch["front_warm"]:
                tags.append("[W]")
            else:
                tags.append("[-]")
        lines.append(f"### 第 {i} 注")
        lines.append(f"前区: {'  '.join(f'{n:02d}' for n in pred['front'])}")
        lines.append(f"后区: {'  '.join(f'{n:02d}' for n in pred['back'])}")
        lines.append(f"标注: {' '.join(tags)}")
        odd = sum(1 for n in pred["front"] if n % 2 == 1)
        even = 5 - odd
        lines.append(f"特征: 奇偶比 {odd}:{even}")
        lines.append("")
    lines.append("---")
    lines.append("免责声明: 彩票开奖是随机事件, 任何分析都不能保证中奖。请理性购彩。")
    return "\n".join(lines)

def push_wechat(report, title="大乐透预测报告"):
    send_key = os.environ.get("SERVERCHAN_KEY", "SCT361365TNYfnOEArgCCcKesZyGnB6z2g")
    url = f"https://sctapi.ftqq.com/{send_key}.send"
    lines = report.split("\n")
    short = []
    for line in lines:
        if line.startswith("#") or line.startswith("---"):
            continue
        short.append(line)
        if len("\n".join(short)) > 1200:
            break
    desp = "\n".join(short)
    data = urllib.parse.urlencode({"title": title, "desp": desp, "short": "大乐透预测已生成"}).encode("utf-8")
    try:
        resp = urllib.request.urlopen(url, data, timeout=10)
        result = json.loads(resp.read().decode("utf-8"))
        if result.get("code") == 0:
            print("已推送到微信")
        else:
            print(f"推送失败: {result.get('message', '')}")
    except Exception as e:
        print(f"推送异常: {e}")

def find_pred_file():
    wd = os.environ.get("GITHUB_WORKSPACE") or os.path.dirname(os.path.abspath(__file__))
    files = sorted(glob.glob(os.path.join(wd, "大乐透预测_*.md")), reverse=True)
    return files[0] if files else None

def parse_pred_file(fp):
    with open(fp, "r", encoding="utf-8") as f:
        text = f.read()
    preds = []
    for block in text.split("### 第")[1:]:
        front = None
        back = None
        for line in block.split("\n"):
            if "前区:" in line:
                nums = [int(x) for x in line.split(":")[-1].strip().split() if x.isdigit()]
                if len(nums) == 5:
                    front = nums
            if "后区:" in line:
                nums = [int(x) for x in line.split(":")[-1].strip().split() if x.isdigit()]
                if len(nums) == 2:
                    back = nums
        if front and back:
            preds.append({"front": front, "back": back})
    return preds

def verify(af, ab, preds):
    res = []
    for p in preds:
        fh = len(set(p["front"]) & set(af))
        bh = len(set(p["back"]) & set(ab))
        res.append({"fh": fh, "bh": bh, "total": fh + bh})
    return res

def update_learn(db, issue, af, ab, preds, results):
    entry = {"issue": issue, "date": datetime.now().strftime("%Y-%m-%d"),
             "af": af, "ab": ab, "predicted": [[p["front"], p["back"]] for p in preds], "results": results}
    for i, h in enumerate(db["history"]):
        if h["issue"] == issue:
            db["history"][i] = entry
            break
    else:
        db["history"].insert(0, entry)
    this_hits = sum(r["total"] for r in results)
    db["total_possible"] = db.get("total_possible", 0) + len(preds) * 7
    db["total_hits"] = db.get("total_hits", 0) + this_hits
    db["rounds"] = db.get("rounds", 0) + 1
    best = max(r["total"] for r in results)
    if best > db.get("best_hit", 0):
        db["best_hit"] = best
    hit_rate = this_hits / (len(preds) * 7) if preds else 0
    w = db["weights"]
    if hit_rate < 0.08:
        w["hot_w"] = max(0.15, w["hot_w"] - 0.02)
        w["cold_w"] = min(0.55, w["cold_w"] + 0.02)
    elif hit_rate > 0.30:
        w["hot_w"] = min(0.60, w["hot_w"] + 0.01)
        w["cold_w"] = max(0.15, w["cold_w"] - 0.01)
    save_learn(db)
    return hit_rate

def format_verify_report(db, issue, af, ab, preds, results):
    lines = []
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"[开奖验证] 第 {issue} 期")
    lines.append(f"实际开奖: 前区 {' '.join(f'{n:02d}' for n in af)} | 后区 {' '.join(f'{n:02d}' for n in ab)}")
    lines.append("")
    lines.append("本期预测命中情况:")
    for i, (p, r) in enumerate(zip(preds, results), 1):
        bar = chr(9608) * r["total"] + chr(9617) * (7 - r["total"])
        lines.append(f"  第{i}注: {bar} 共命中{r['total']}/7 (前区{r['fh']}个, 后区{r['bh']}个)")
    best = max(r["total"] for r in results)
    lines.append("")
    lines.append(f"本期最佳: {best}/7")
    hit_rate = db["total_hits"] / max(db["total_possible"], 1) * 100
    lines.append(f"累计验证: {db['rounds']}期 | 综合命中率 {hit_rate:.1f}% | 最佳单注 {db['best_hit']}/7")
    lines.append("=" * 60)
    lines.append("")
    return "\n".join(lines)

def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "predict"
    
    if mode == "verify":
        # Verify + learn + predict next
        print("[验证模式] 获取最新开奖数据...")
        history = fetch_history(5)
        if not history:
            print("获取开奖数据失败")
            return
        latest = history[0]
        db = load_learn()
        pf = find_pred_file()
        if not pf:
            print("未找到预测文件")
            return
        preds = parse_pred_file(pf)
        if not preds:
            print("解析预测文件失败")
            return
        af = latest["front"]
        ab = latest["back"]
        results = verify(af, ab, preds)
        issue = latest["issue"]
        hit_rate = update_learn(db, issue, af, ab, preds, results)
        report = format_verify_report(db, issue, af, ab, preds, results)
        print(report)
        push_wechat(report, f"[验证] 第{issue}期开奖验证")
        # Generate next prediction
        print("[验证模式] 正在生成下一期预测...")
        history2 = fetch_history(80)
        ch = analyze_cold_hot(history2)
        zs = analyze_zones(history2)
        oe = analyze_odd_even(history2)
        bz = analyze_back_zones(history2)
        predictions = generate_predictions(history2, ch)
        rep = generate_report(history2, ch, zs, oe, bz, predictions)
        fn = f"大乐透预测_第{history2[0]['issue']}期_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        fp = os.path.join(WORK_DIR, fn)
        with open(fp, "w", encoding="utf-8") as f:
            f.write(rep)
        print(f"下一期预测已保存: {fn}")
                        db["last_pred_file"] = fn
                        save_learn(db)
    db["last_pred_file"] = fn
    save_learn(db)
        push_wechat(rep, f"[预测] 第{history2[0]['issue']}期大乐透预测")
        return
    
    # Predict mode (original)
    print("正在获取历史开奖数据...")
    history = fetch_history(80)
    print(f"获取到 {len(history)} 期历史数据")
    print(f"最新一期: 第 {history[0]['issue']} 期 ({history[0]['date']})")
    print("正在进行多维分析...")
    ch = analyze_cold_hot(history)
    zs = analyze_zones(history)
    oe = analyze_odd_even(history)
    bz = analyze_back_zones(history)
    print("正在生成预测号码...")
    predictions = generate_predictions(history, ch)
    print("正在生成报告...")
    report = generate_report(history, ch, zs, oe, bz, predictions)
    fn = f"大乐透预测_第{history[0]['issue']}期_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
    fp = os.path.join(os.getcwd(), fn)
    with open(fp, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"报告已保存: {fn}")
    print("正在推送到微信...")
    push_wechat(report)
    print(f"\n完整报告: {fn}")

if __name__ == "__main__":
    main()

