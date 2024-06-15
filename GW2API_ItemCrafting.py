import requests
import json
import pickle
from time import sleep

# itemList is a dict. ID : name

#Function for API calling so that it doesn't clog up the code
#Make the API call to the specified place. Check if we hit the limit. If we did, wait 2 seconds to regain 10 API calls and continue
#Return the .json()
def APICall(extension, ID, ignore = False):
    link = requests.get('https://api.guildwars2.com/v2/' + extension + ID, timeout = 2)
    if link.status_code == 429:
        print("We have hit the limit on API requests. Temporarily sleeping to regain uses of the API...")
        sleep(1)
        print("...zzz...")
        sleep(1)
        print("10 uses regained, continuing...\n")
        link = requests.get('https://api.guildwars2.com/v2/' + extension + ID, timeout = 2)
    if link.status_code != requests.codes.ok:
        print("An API request to " + extension + " has failed")
        if not ignore: exit(1)
        else: return None
    return link.json()



#Function to calculate the cost of buying a material
#ID is a comma-separated STRING of item IDs
#This returns sellValuse, a DICTIONARY that matches an item ID to a list of the BUY value [0] and SELL value [1]
def sellInfo(ID):
    sellValues = {}
    TPInfo = APICall('commerce/prices?ids=', ID)
    for item in TPInfo:
        baseBuy = item['buys']['unit_price']
        baseSell = item['sells']['unit_price']
        sellValues[item['id']] = [baseBuy, baseSell]
    return sellValues



def getRecipes(itemID, recipeList = None, itemToRecipe = None):
    potentialRecipes = {}
    if recipeList is None : recipeList = {}
    if itemToRecipe is None : itemToRecipe = {}
    recipesToCheck = [itemID]
    #Keep going until we reach every recipe that has ingredients stemming from the given ID
    while not recipesToCheck:
        idsToCheck = []
        #For every ID we have, we need to grab the recipes that use it as an ingredient
        for id in recipesToCheck:
            if id in itemToRecipe and itemToRecipe[id][0] != False:
                #If our job is easy, add every recipe in storage to the idsToCheck to look at later
                for useID in itemToRecipe[id][0]:
                    potentialRecipes[useID] = [False, []]
                    idsToCheck.append(useID)
            #If our job is not easy, ping the API. Unfortunately, the recipes/search DOES NOT take multiple ids. WE HAVE TO GO ONE BY ONE
            #WHY IS IT LIKE THIS. WHY MUST I SUFFER. I FUCKING IMPORTED TIME AND DID AN EXTRA CHECK JUST TO BE SURE THAT WE DON'T EXCEED THE LIMITS BECAUSE OH MY GOD WE'RE GOING TO EXCEED THE LIMITS
            #300 requests per minute. Some base materials (Ancient wood log) would probably hit this limit almost immediately. Especially later when we have to go -DOWN-
            #Replenishes 5 requests per second. If we go over, we will wait **2** seconds. THIS IS WHY I RECOMMEND SAVING RECIPES AT THE COST OF SPACE.
            else:
                recipeOutput = APICall('recipes/search?input=', id)
                #Same thing as above, initialize the cost as False and add to the check list. Now, we also add it to itemToRecipe for future use
                itemToRecipe[id] = [set(recipeOutput), False]
                for recipeID in recipeOutput:
                    potentialRecipes[recipeID] = [False, []]
                    idsToCheck.append(recipeID)

        #We now have recipes to check for the output ID (idsToCheck) so that we can continue the loop.
        recipesToCheck = []
        if idsToCheck:
            unknownRecipeIDs = []
            #If we have the recipe, just grab the output ID and we'll check it later. Otherwise, add it to a list of IDs to call the API for
            for recipeID in idsToCheck:
                if recipeID in recipeList:
                    recipesToCheck.append(recipeList[recipeID][1][0])
                else:
                    unknownRecipeIDs.append(recipeID)
            
            #Go through the IDs until we've checked them all
            while unknownRecipeIDs:
                strID = ""
                #API has a limit of 200 ids per request
                if len(unknownRecipeIDs) > 200:
                    for i in range(200):
                        strID = strID + str(unknownRecipeIDs[i]) + ","
                    unknownRecipeIDs = unknownRecipeIDs[200:]
                else:
                    for i in unknownRecipeIDs:
                        strID = strID + str(i) + ","
                    unknownRecipeIDs = []
                
                #Make the API call to get all the recipe data
                response = APICall('recipes?ids=', strID)
                for reply in response:
                    # recipeList = Recipe ID : [[list of ingredient IDs, quantity, type], [output ID, quantity], [discipline, rating]]
                    ingredients = []
                    for ingrd in reply['ingredients']:
                        thisIngrd = [ingrd['id'], ingrd['count'], ingrd['type']]
                        ingredients.append(thisIngrd)
                    recipeList[reply] = [
                        [
                            ingredients
                        ]
                        [
                            reply['output_item_id'],
                            reply['output_item_count']
                        ]
                        [
                            reply['disciplines'],
                            reply['min_rating']
                        ]
                    ]
                    recipesToCheck.append(reply['output_item_id'])
    
    #After the loop, we've gone up through every recipe! We have all the potential recipes, recipe info, and item info, so time to return it!
    return recipesToCheck, recipeList, itemToRecipe



def craftCost(potentialRecipes, recipeList, itemToRecipe):
    #We start by, sadly, going through the recipes we don't know. We make as many API calls as we can at this point to get it out of the way
    print("Beginning recipe accumulation. This may take a moment depending on how many recipes have been stored, if that option was selected...")






def main():
    #Init
    response = requests.get('https://api.gw2tp.com/1/bulk/items-names.json', timeout = 2)
    if response.status_code != requests.codes.ok:
        print("The GW2TP API appears to be unresponsive. Please try again later.")
        exit(1)
    else:
        response = response.json()
    response = response['items']
    print("Welcome to the Item Crafting Checker! This will see if it is more profitable to craft something with those pesky items, or if you should just sell them!\n")

    toCheckItems = []

    #Create/Maintain the file. It is a dictionary of IDs matched to names and a vendor value. What we grab from the API is a list.
    try:
        file = open("itemList.pickle", "rb")
        itemList = pickle.load(file)
        if response[-1][0] not in itemList:
            print("One moment while we update the stored items...")
            point = -1
            index = response[point]
            while index[0] not in itemList:
                #We initialize the vendor value to -1 as a signal that we will need to update this later in a batched process. Doing it one by one is too API-intensive
                itemList[index[0]] = [index[1], -1]
                toCheckItems.append(index[0])
                point -= 1
                index = response[point]
        storeRecipes = itemList['recipe']
        if storeRecipes:
            try:
                recipeList = pickle.load(file)
                itemToRecipe = pickle.load(file)
            except:
                recipeList = {}
                itemToRecipe = {}
        haveSkins = itemList['skins']
        #If we should prioritize fashion, grab the list of unlocked skins from the API since it has likely changed since last time
        if haveSkins:
            skinResponse = requests.get('https://api.guildwars2.com/v2/account/skins?access_token=' + itemList['API'], timeout = 2)
            if skinResponse.status_code == 403:
                print("It appears that the key provided was not valid or did not have the necessary permissions. Please ensure your key is updated.")
                print(itemList['API'])
                #TODO: Allow for updating of API key
            elif skinResponse.status_code != requests.status_codes.ok:
                print("There was a problem accessing the API. This does not mean your API key is invalid. Please try again later.")
                exit(1)
            else:
                skinResponse = skinResponse.json()
                #Make it a set so we can VERY quickly check if an ID is in the set or not
                skinSet = set(skinResponse)
        file.close()
                
    #Create the file if it doesn't exist
    except OSError:
        print("Looks like there's not a stored list of items! \nOne moment while we create this list. It may take a second...\n")
        file = open("itemList.pickle", "wb")
        itemList = {}
        for pair in response:
            itemList[pair[0]] = [pair[1], -1]
            toCheckItems.append(pair[0])
        #The recipe list is accumulated, not initialized. There is too much information to grab and also some auxillary information i.e output name and ingredient names.
        input = ("Item list complete! Would you like to also store recipe information?\nThis is HIGHLY recommended. The program will take up more space, but will allow you to use the program more often without being locked out by the GW2 API.\n" + 
                 "Note: These lists are accumulated. The program may run slow at first, but will rapidly speed up as it gathers more recipe information.\nType yes/no : ")
        if input.lower() == 'yes' :
            storeRecipes = itemList['recipe'] = True
        else:
            storeRecipes = itemList['recipe'] = False
        while True:
            input = ("\nWould you like to prioritize crafting skins you do not have? To do this, we will need an API key with access to your 'Unlocks'.\nPaste your API key here. If you do not want this, leave the space empty and press enter : ")
            if input:
                skinResponse = requests.get('https://api.guildwars2.com/v2/account/skins?access_token=' + input, timeout = 2)
                if skinResponse.status_code == 403:
                    print("It appears that the key provided was not valid or did not have the necessary permissions. Please try again.")
                elif skinResponse.status_code != requests.codes.ok:
                    print("Something went wrong, but the key appears to be fine. Please try again later.")
                    exit(1)
                else:
                    skinResponse = skinResponse.json()
                    haveSkins = itemList['skins'] = True
                    itemList['API'] = input
                    skinSet = set(skinResponse)
                    break
            else:
                haveSkins = itemList['skins'] = False
                break
        pickle.dump(itemList, file)
        file.close()

    
    #Start the while loop that will run until the user exits the program
    while True:
        #Get user input for the item. Bug them until they give us something we can use
        while success := False != True:
            item = input("To exit the program, please type 'exit'. If you believe some cached recipe or item data may be incorrect, type 'clear'\nWhich item do you want to search for? (This is case sensitive, type it as it appears in-game): ")
            item = item.strip()
            if item.lower() == 'exit':
                #TODO : HANDLE CLOSING THINGS LIKE SAVING RECIPES AND CLEARING OUT toCheckItems
                exit(0)
            if item.lower() == 'clear':
                #TODO : CLEAR OUT FILES AND START FROM SCRATCH
                exit(0)
            #We loop through the inital item list in order to grab the item ID. We must do a slow search like this since all internal / server code uses item IDs, not names.
            #I did not think it was worth storing a reversed dictionary -just- for this single part of the code.
            for pair in response:
                if item == response[1]:
                    itemID = str(response[0])
                    itemInfo = APICall('items/', itemID, True)
                    success = True
                    break
            if not success:
                print("Sorry, it doesn't look like that item is in our list.")
                itemID = input("Do you know the ID of the item? This can be found on the Guild Wars 2 Wiki as the API listing (i.e 46742)\nIf you don't know the ID or wish to try again, press Enter : ")
                if itemID:
                    itemInfo = APICall('items/', itemID, True)
                    if itemInfo != None:
                        success = True
        
        #We now have the itemID and itemInfo from the item itself
        potentialRecipes, recipeList, itemToRecipe = getRecipes(itemID, recipeList, itemToRecipe)
        
        #Re-link the potential recipes so that we can cut down on how many API calls we have to make
        #For every recipe, check the ingredients and see which recipes create those ingredients
        for initRecipe in potentialRecipes:
            for ingredient in recipeList[initRecipe][0]:
                if ingredient[2] == 'Item':
                    ingrdID = ingredient[0]
                    for craftRecipe in potentialRecipes:
                        #Once we find the correct link, we note it down
                        if recipeList[craftRecipe][1][0] == ingrdID:
                            potentialRecipes[initRecipe][1].append(craftRecipe)
                            
        #Now that we have all the potential recipes, we need to start working back DOWN and grabbing all of the crafting costs




main() 

#response = requests.get('https://api.guildwars2.com/v2/recipes/search')
#print(response.json())

#Flow:
#Receive item
# Initiate cost as TP price
# --- Search for recipes that use it
# Loop until there are no more recipes to look at upwards (~4-5 requests)
# Check output items for all recipes
#   If they are account bound / soul bound, disregard. Otherwise, hold onto the ID
# Loop through ALL recipes, all the way up and down
# Check if there is a profit
# Repeat this for everything that uses the output as a recipe as well
# Add everything into a nice, neat format!

# TODO: REMEMBER TRADING POST FEES

# FOR THE API!! 200 IDS IS THE LIMIT

# The most profitable item is:
# Recipe name (output) - Sells for this much on the TP
# 	Material 1 - Costs this much to craft / acquire on the TP
# 		If craft, more materials
#	Material 2 - TP
#	Material 3 - Currency
# Repeat per profitable recipe in descending order


# SAVED INFO

# ItemList = ID : name, can be sold on TP?, vendor value, default skin
#	SPECIAL
#		ItemList['recipe'] = RecipeList exists?
#		ItemList['skins'] = SkinSet exists?
# recipeList = Recipe ID : [[list of ingredient IDs, quantity, type], [output ID, quantity], [discipline, rating]]
# itemToRecipe = Item ID : [{list of recipe IDs that use the item}, {list of recipe IDs that make the item}]

# PER - RUN INFO

# SkinSet = set of unlocked skins
# itemInfo = ID : [buyCost, sellCost]
# recipeInfo = ID : craftCost, [recipes that make ingredients]

# IF NOT STORING RECIPES
# recipeList and itemToRecipe are just variables

# outputList = [recipe IDs sorted by profit]
#	From the IDs, we can grab output ID / names, discipline / rating, and then list all materials + whether to craft or buy