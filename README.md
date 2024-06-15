# Guild Wars 2 Recipe Calculator (Currently incomplete and a work in progress)
A calculator to take in a specific item, sift through the trading post, and find the most profitable way to utilize the item. Includes an optional local storage of item recipes which is *highly* recommended.

Due to limitations with the Guild Wars 2 API, this will generate quite a few requests when trying to work down the crafting tree. As such, it's recommended to enable to local storage of recipes so that subsequent recipe searches are faster. The first one will likely be delayed from excessive API calls.

This program will, at minimum, store a list of items within Guild Wars 2. Storing recipe information will increase the size and is optional but recommended. It also offers prioritization of crafting skins that you do not currently own, which will require a valid API key with the 'Unlocks' permission (see https://wiki.guildwars2.com/wiki/API:API_key )
