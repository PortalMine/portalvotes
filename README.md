# portalvotes
A further STEEM votebot derived from the "old" [curationvoter](https://github.com/PortalMine/curationvoter). Customizable with config file and stable on my RasPi.

***
### Features
The votebot got 4 python files, one config file and several files for further customisation.
* voting_loop.py: When the voting power of the attached account climbs over a certain value, it will vote the next new post matching all specified conditions. You can freely set the voting delay. So the bot waits until your VP is at e.g. 95% and then starts searching matching posts. When a post is found, it checks if the author is eventually blacklisted, has a minimum reputation score and so on. If all criteria are fulfilled, it will vote the post on it's age of e.g. 15 minutes. Posts older than 30 minutes are edits for sure and will be ignored for voting. The vote weight used is defined in the config file. You can configure the bot to leave a comment below the voted post (comment text is read from ```/files_voter/comment.txt```). This gives you the chance of getting additional author rewards.
* poster_2.py: When started, the script reads all votes of the account from the blockchain, puts them together into a table and publishes a post like you have written into the ```/files_poster/post.txt``` while replacing "[DATE]" and "[TABLE_POSTS]" with the current date and the votes done by the last vote included in the last post done by the posting script.
* one_per_week.py: This script fills the ```/files_voter/dynamic_blacklist_users.txt``` with all user names voted in the last seven days. This script is optional to use and only written for my personal use at [@portalvotes](https://steemit.com/@portalvotes/). But it's useful to distribute your votes more widely.
* claim.py: Simply claims all released reward payments of the bot account. Optional but useful for full automation.

***
### Dependencies
You will need a Python3.x interpreter.
Additional python packages to install:
* beem (essential as it is the API to connect to the STEEM blockchain)
* configparser (if not installed with python installation, essential)
* Markdown (used in the posting script, you don't need that if you don't publish voting report posts)

***
### My Setup
Everything is running on my Raspberry Pi 3B+ with the newest Raspbian version.
The scripts are started by bash scripts started by crontab. For asking people: The bash scripts are nessecary, otherwise the pythin scripts would run in the root directory and couldn't find any required files like the config.ini
* voting_loop.py is started once (start.sh)
* everydays 17:30 a post is published (post.sh)
* every four hours my optional user blacklist is updated (one_per_week.sh)
* each half hour I try to claim rewards (claim.sh)

So, for my case the crontab file (accessible via ```crontab -e```) looks like this:
```
@reboot python3 //home/pi/portalvotes_2/start.sh &
30 17 * * * python3 //home/pi/portalvotes_2/post.sh
00 */4 * * * python3 //home/pi/portalvotes_2/one_per_week.sh
*/30 * * * * python3 //home/pi/portalvotes_2/claim.sh
```
