import src.autobastian as atb
import time, datetime

'''
https://www.github.com/soulspine/autobastian
Works as of 27.04.2024
'''

if __name__ == "__main__":
    config:atb.Config = atb.Config()
    bot = atb.Bot(config)

    # menu with options:
        # selecting to run the bot in cycles
        # selecting to run once
        # selecting to run the metadata updater

    while True:
        try:
            bot.cycle()
            time.sleep(config.sleepTime)
        except KeyboardInterrupt: exit()
        except Exception as e:
            bot.log(f"Error - {e}")
            if config.ignoreErrors: continue
            break