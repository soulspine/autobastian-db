import src.autobastian as atb
import time, datetime

'''
Windows release
Works as of 08.05.2024
'''

if __name__ == "__main__":
    config:atb.Config = atb.Config()
    bot = atb.Bot(config)

    while True:
        try:
            bot.cycle()
            time.sleep(config.sleepTime)
        except KeyboardInterrupt: exit()
        except Exception as e:
            bot.log(f"Error - {e}")
            if config.ignoreErrors: continue
            break