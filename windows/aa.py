#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import subprocess
import datetime
import time
import sys
try:
    # Python 3.9+
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
except ImportError:
    # Python 3.8以下 (要 pip install pytz)
    try:
        from pytz import timezone, UnknownTimeZoneError
        # zoneinfoのインターフェースに似せるためのラッパー
        class ZoneInfoWrapper:
            def __init__(self, tz_name):
                try:
                    self._tz = timezone(tz_name)
                except UnknownTimeZoneError:
                    # pytz にない場合、システムDBに存在するか試す (Windowsでは限定的)
                    try:
                         # datetime.timezoneにはUTCオフセットしか渡せないため直接は使えない
                         # ZoneInfoNotFoundErrorを発生させるのが一貫性がある
                         raise UnknownTimeZoneError(f"Timezone '{tz_name}' not found using pytz.")
                    except Exception:
                         raise ZoneInfoNotFoundError(f"Timezone '{tz_name}' not found using pytz or system.")

            def normalize(self, dt): return self._tz.normalize(dt)
            def localize(self, dt): return self._tz.localize(dt)
            # zoneinfoとの互換性のためのメソッドスタブ
            def from_file(self, fobj, key=None): raise NotImplementedError
            def no_cache(self): return self
            @property
            def key(self): return self._tz.zone

        ZoneInfo = ZoneInfoWrapper # ZoneInfoとして使えるように代入
        print("警告: zoneinfoモジュールが見つかりません。pytzを使用します (pip install pytz が必要)。", file=sys.stderr)

    except ImportError:
        print("エラー: タイムゾーン処理のために zoneinfo (Python 3.9+) または pytz が必要です。", file=sys.stderr)
        print("pytz をインストールしてください: pip install pytz", file=sys.stderr)
        sys.exit(1)
    except NameError: # ZoneInfoNotFoundError が pytz にない場合
        class ZoneInfoNotFoundError(Exception): pass


# --- 設定 ---
# !!! 注意: 実際のWindows環境に合わせてパスを変更してください !!!
# os.path.expanduser("~") はユーザーのホームディレクトリを取得します
output_dir = os.path.join(os.path.expanduser("~"), "speedtest")
output_file = os.path.join(output_dir, "output.csv")
# speedtest_executable = os.path.join(os.path.expanduser("~"), "speedtest", "speedtest.exe")
# もし環境変数PATHが通っているなら 'speedtest.exe' だけで良い場合もある
speedtest_executable = 'speedtest.exe' # 環境に合わせてフルパスを指定推奨

server_id = "48463"
output_encoding = "utf-8" # 出力ファイルの文字コード

# --- 定期実行設定 ---
OFFSET_MINUTES = 3  # 毎時 0+n分, 10+n分, ..., 50+n分 の n の値 (例: 2なら 02分, 12分, ..., 52分)
TIMEZONE = "Asia/Tokyo" # 実行タイミングの基準とするタイムゾーン

# --- グローバル変数 ---
tokyo_tz = None

# --- 関数 ---

def setup_timezone():
    """タイムゾーンオブジェクトを初期化"""
    global tokyo_tz
    try:
        tokyo_tz = ZoneInfo(TIMEZONE)
    except ZoneInfoNotFoundError:
        print(f"エラー: タイムゾーン '{TIMEZONE}' が見つかりません。", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"エラー: タイムゾーン設定中に予期せぬエラー: {e}", file=sys.stderr)
        sys.exit(1)

def get_current_time() -> datetime.datetime:
    """指定されたタイムゾーンでの現在時刻を取得"""
    if tokyo_tz is None:
        setup_timezone()
    # naïveな現在時刻を取得し、タイムゾーン情報を付与する
    # now_naive = datetime.datetime.now()
    # if hasattr(tokyo_tz, 'localize'): # pytzの場合
    #     return tokyo_tz.localize(now_naive)
    # else: # zoneinfoの場合
    #     return now_naive.replace(tzinfo=tokyo_tz)
    # より確実な方法: UTCを取得してから変換する
    return datetime.datetime.now(datetime.timezone.utc).astimezone(tokyo_tz)


def calculate_next_run_time(current_time: datetime.datetime, offset_minutes: int) -> datetime.datetime:
    """次の実行時刻（毎10分+オフセット）を計算。直近の未来の実行時刻を返す。"""
    # 最新の現在時刻を取得して比較の基準とする
    # 関数呼び出し時の current_time ではなく、計算直前の現在時刻を使う方がより正確
    now = get_current_time()

    # --- ターゲット時刻1の計算 (現在の10分ブロック + オフセット) ---
    # 1. 現在の10分ブロックの開始分を計算 (例: 47分 -> 40分)
    current_base_minute_relative = (now.minute // 10) * 10

    # 2. ターゲットとなる絶対分を計算 (繰り上がり考慮)
    #    (例: 23時40分 + 8分 = 23時48分に対応する絶対分)
    target1_minute_abs = now.hour * 60 + current_base_minute_relative + offset_minutes

    # 時と分に分割し、日付変更も考慮
    target1_hour_abs = target1_minute_abs // 60
    target1_minute_final = target1_minute_abs % 60
    target1_date = now.date() + datetime.timedelta(days = target1_hour_abs // 24)
    target1_hour_final = target1_hour_abs % 24

    # ターゲット時刻1のnaive datetimeを作成
    target1_naive = datetime.datetime.combine(target1_date, datetime.time(hour=target1_hour_final, minute=target1_minute_final))

    # タイムゾーン情報を付与
    if hasattr(now.tzinfo, 'localize'): # pytz
        target1_time = now.tzinfo.localize(target1_naive)
    else: # zoneinfo
        try:
             target1_time = target1_naive.replace(tzinfo=now.tzinfo)
        except Exception as e:
             # DST遷移などでエラーになる可能性への対応（例）
             print(f"警告: ターゲット時刻1 ({target1_naive}) のタイムゾーン設定でエラー: {e}。UTCオフセットで試みます。", file=sys.stderr)
             target1_time = target1_naive.replace(tzinfo=datetime.timezone(now.utcoffset()))


    # --- 判定と、必要ならターゲット時刻2の計算 ---
    # 3. ターゲット時刻1が未来ならそれを採用
    if target1_time > now:
        # print(f"デバッグ: ターゲット1 {target1_time.strftime('%H:%M:%S')} が現在 {now.strftime('%H:%M:%S')} より未来のため採用")
        return target1_time
    else:
        # print(f"デバッグ: ターゲット1 {target1_time.strftime('%H:%M:%S')} が現在 {now.strftime('%H:%M:%S')} より過去または同じ")
        # 4. ターゲット時刻1が過去または現在の場合、次の10分ブロックを基準にする
        #    (例: 現在47分 -> 次のブロック開始は50分)
        next_base_minute_relative = ((now.minute // 10) + 1) * 10

        # 5. ターゲット時刻2 (次のブロックベース) を計算
        target2_minute_abs = now.hour * 60 + next_base_minute_relative + offset_minutes

        # 時と分に分割し、日付変更も考慮
        target2_hour_abs = target2_minute_abs // 60
        target2_minute_final = target2_minute_abs % 60
        target2_date = now.date() + datetime.timedelta(days = target2_hour_abs // 24)
        target2_hour_final = target2_hour_abs % 24

        # ターゲット時刻2のnaive datetimeを作成
        target2_naive = datetime.datetime.combine(target2_date, datetime.time(hour=target2_hour_final, minute=target2_minute_final))

        # タイムゾーン情報を付与
        if hasattr(now.tzinfo, 'localize'): # pytz
            target2_time = now.tzinfo.localize(target2_naive)
        else: # zoneinfo
            try:
                target2_time = target2_naive.replace(tzinfo=now.tzinfo)
            except Exception as e:
                print(f"警告: ターゲット時刻2 ({target2_naive}) のタイムゾーン設定でエラー: {e}。UTCオフセットで試みます。", file=sys.stderr)
                target2_time = target2_naive.replace(tzinfo=datetime.timezone(now.utcoffset()))


        # print(f"デバッグ: ターゲット2 {target2_time.strftime('%H:%M:%S')} を採用")
        # 6. ターゲット時刻2を返す (これは必ず未来のはず)
        return target2_time

def run_speedtest(executable: str, server: str, encoding: str) -> str | None:
    """Speedtestを実行し、CSV形式の出力を返す。エラー時はNoneを返す。"""
    try:
        result = subprocess.run(
            [executable, f"--server-id={server}", "--format=csv"],
            capture_output=True, # これがTrueならstdoutとstderrの両方をキャプチャする
            text=True,
            encoding=encoding,
            # stderr=subprocess.PIPE, # この行を削除またはコメントアウトする
            check=True # 終了コード0以外で例外発生
        )
        # オプション: 成功時でも標準エラー出力に何か出ていないか確認
        # if result.stderr:
        #     print(f"警告: Speedtest実行中に標準エラー出力がありました:\n{result.stderr.strip()}", file=sys.stderr)

        # 前後の空白と末尾の改行を削除
        speedtest_part = result.stdout.strip()
        return speedtest_part
    except FileNotFoundError:
        print(f"エラー: Speedtest実行ファイルが見つかりません: {executable}", file=sys.stderr)
        return None
    except subprocess.CalledProcessError as e:
        print(f"エラー: Speedtestの実行に失敗しました。終了コード: {e.returncode}", file=sys.stderr)
        # capture_output=True なので、エラー時の stderr は e.stderr でアクセスできる
        if e.stderr:
            print(f"エラー出力:\n{e.stderr.strip()}", file=sys.stderr)
        return None
    except Exception as e:
        # エラーの原因が TypeError であることを特定しやすくするため、型を確認してもよい
        # if isinstance(e, TypeError):
        #     print(f"エラー: subprocess.runの引数に問題があります: {e}", file=sys.stderr)
        # else:
        #     print(f"エラー: Speedtest実行中に予期せぬエラーが発生しました: {e}", file=sys.stderr)
        print(f"エラー: Speedtest実行中に予期せぬエラーが発生しました: {e}", file=sys.stderr)
        return None

def append_to_file(filepath: str, line: str, encoding: str):
    """指定されたファイルに行を追記する"""
    try:
        # ディレクトリが存在しない場合は作成
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'a', encoding=encoding) as f:
            f.write(line)
    except IOError as e:
        print(f"エラー: ファイル '{filepath}' への書き込み中にエラーが発生しました: {e}", file=sys.stderr)
    except Exception as e:
        print(f"エラー: ファイル書き込み中に予期せぬエラーが発生しました: {e}", file=sys.stderr)


# --- メイン処理 ---
def main():
    setup_timezone()
    print(f"スクリプト開始 (PID: {os.getpid()})")
    print(f"出力ファイル: {output_file}")
    print(f"実行タイミング: 毎時 {OFFSET_MINUTES:02d}, {10+OFFSET_MINUTES:02d}, ..., {50+OFFSET_MINUTES:02d} 分 ({TIMEZONE})")
    print(f"SpeedtestサーバーID: {server_id}")
    print("Ctrl+Cで終了します。")

    while True:
        try:
            # 1. 現在時刻取得
            now = get_current_time()

            # 2. 次の実行時刻計算
            next_run_time = calculate_next_run_time(now, OFFSET_MINUTES)
            print("-" * 30)
            print(f"現在時刻:         {now.strftime('%Y-%m-%d %H:%M:%S %Z (%z)')}")
            print(f"次の実行予定時刻: {next_run_time.strftime('%Y-%m-%d %H:%M:%S %Z (%z)')}")

            # 3. スリープ時間計算と待機
            wait_seconds = (next_run_time - now).total_seconds()
            if wait_seconds > 0:
                print(f"待機します: {wait_seconds:.1f} 秒")
                # time.sleep()は中断される可能性があるので、短いスリープを繰り返す方が堅牢
                # ここではシンプルに time.sleep() を使う
                time.sleep(wait_seconds)
            else:
                # 予定時刻を過ぎている場合（計算直後に実行時刻になったなど）
                print("ほぼ実行時刻です。すぐに処理を開始します。")
                # 念のため非常に短い待機を入れるとCPU使用率を抑えられることがある
                time.sleep(0.1)

            # --- 処理実行 ---
            print(f"実行開始: {get_current_time().strftime('%Y-%m-%d %H:%M:%S')}")
            process_start_mono = time.monotonic()

            # 4. 日時部分を取得 (処理開始直前の時刻)
            process_start_time_obj = get_current_time() # 実行直前の時刻を記録
            datetime_part = process_start_time_obj.strftime('"%Y-%m-%d %H:%M:%S",')

            # 5. Speedtest実行
            speedtest_part = run_speedtest(speedtest_executable, server_id, output_encoding)

            process_end_mono = time.monotonic()
            duration = process_end_mono - process_start_mono
            print(f"Speedtest完了 (所要時間: {duration:.2f}秒)")

            # 6. 結果を連結してファイルに追記
            if speedtest_part is not None:
                output_line = f"{datetime_part}{speedtest_part}\n" # 末尾に改行を追加
                append_to_file(output_file, output_line, output_encoding)
                print(f"結果を {output_file} に追記しました。")
            else:
                print("Speedtestが失敗したため、ファイルへの書き込みをスキップしました。")

            # 次のループへの短い待機 (任意、CPU負荷軽減のため)
            # time.sleep(1)

        except KeyboardInterrupt:
            print("\nCtrl+Cが押されました。スクリプトを終了します。")
            break # ループを抜ける
        except Exception as e:
            # 予期せぬエラーが発生してもループを継続できるようにログ出力して待機
            print(f"\n!!! ループ内で予期せぬエラーが発生しました: {e} !!!", file=sys.stderr)
            # エラー発生時は少し長めに待つなど検討
            print("1分待機して処理を継続します...", file=sys.stderr)
            time.sleep(60)

    print("スクリプト終了。")
    sys.exit(0)

if __name__ == "__main__":
    main()