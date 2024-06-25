import requests
import json
import pickle
import math
from time import sleep


CONST_DEFAULT_LINK = 'https://api.guildwars2.com/v2/'

#Function for API calling so that it doesn't clog up the code
#Make the API call to the specified place. Check if we hit the limit. If we did, wait 2 seconds to regain 10 API calls and continue
#The version parameter is specifically for the recipes to return the types of ingredients correctly
#Return the .json()
def APICall(extension : str, ID : str, ignore = False, link : str = CONST_DEFAULT_LINK):
    response = requests.get(link + extension + ID + "&v=2022-03-09T02:00:00.000Z", timeout = 2)
    error = None
    match response.status_code:
        case 429:
            print("We have hit the limit on API requests. Temporarily sleeping to regain uses of the API...")
            sleep(1)
            print("...zzz...")
            sleep(1)
            print("10 uses regained, continuing...\n")
            return APICall(extension, ID, ignore, link)
        case 403:
            print("The given API key appears to be invalid, or does not have the necessary permissions")
            print(ID)
            error = 403
        case 404:
            print("Endpoint does not exist, or all IDs somehow got corrupted")
            print(ID)
            error = 404
        case 502 | 504:
            print("The Guild Wars 2 server ran into an error. Please try again later")
            error = 502
        case 503:
            print("Given endpoint is disabled. Program will not work until it is updated. Bug the developer.")
            error = 503
        case _:
            return response.json()
        
    if not ignore:
        exit(1)
    else:
        return error



#Function to consolidate a list into a string to fit the API id limit
#Modifies IDList and returns a string
def truncate(IDList : list):
    strID = ""
    if len(IDList) > 200:
        for i in range(200):
            strID += str(IDList[i]) + ","
        IDList = IDList[200:]
    else:
        for i in IDList:
            strID += str(i) + ","
        IDList.clear()
    return strID



#Function to get a list of ids and gather + sort all the info
#Takes in the list of IDs and returns a dictionary that can be merged with recipeList AND a list of IDs that each recipe outputs
def recipeAPICall(IDList : list):
    recipeList = {}
    returnIDs = []
    while IDList:
        strID = truncate(IDList)
        
        #Get all the recipe data from our current limit
        response = APICall('recipes?ids=', strID)
        for reply in response:
            # recipeList = Recipe ID : [[list of ingredient IDs, quantity, type], [output ID, quantity], [discipline, rating]]
            #Gather all the ingredients into an array
            ingredients = []
            for ingrd in reply['ingredients']:
                thisIngrd = [ingrd['id'], ingrd['count'], ingrd['type']]
                ingredients.append(thisIngrd)
            recipeList[reply] = [
                ingredients,
                [
                    reply['output_item_id'],
                    reply['output_item_count']
                ],
                [
                    reply['disciplines'],
                    reply['min_rating']
                ]
            ]
            returnIDs.append(reply['output_item_id'])
    
    return recipeList, returnIDs



#Function to calculate the cost of buying a material
#ID is a comma-separated STRING of item IDs
#This returns sellValues, a DICTIONARY that matches an item ID to a list of the BUY value [0] and SELL value [1]
def sellInfo(ID : str):
    sellValues = {}
    TPInfo = APICall('commerce/prices?ids=', ID)
    for item in TPInfo:
        baseBuy = item['buys']['unit_price']
        baseSell = item['sells']['unit_price']
        sellValues[item['id']] = [baseBuy, baseSell]
    return sellValues



#Simple wrapper for truncation and sellInfo
def commerceAPICall(IDList : list):
    priceInfo = {}
    while IDList:
        strID = truncate(IDList)
        priceInfo.update(sellInfo(strID))
    return priceInfo



#Calls the items API resource. Takes in a list of IDs and itemList, and returns commerceIDList with itemList being modified
#Will gather all item info if it is not present in itemList
def itemAPICall(IDList : list, itemList : dict):
    commerceIDs = []
    strID = truncate(IDList)
    response = APICall("items?ids=", strID)
    for reply in response:
        #Gather all the info and put it into the itemList
        if reply['id'] not in itemList:
            print("Found and item that was not in the list? ID : {}, and name : {}".format(reply['id'], reply['name']))
            itemList['id'] = [reply['name'], None, None, None]
        
        vendorValue, TPSell, skinID = None
        if 'vendor_value' in reply and 'NoSell' not in reply['flags']:
            vendorValue = reply['vendor_value']
        else:
            vendorValue = False
        
        if 'AccountBound' not in reply['flags'] and 'SoulbindOnAcquire' not in reply['flags']:
            TPSell = True
            commerceIDs.append(reply['id'])
        else:
            TPSell = False
        
        if 'default_skin' in reply:
            skinID = reply['default_skin']
        else:
            skinID = False
        
        itemList['id'] = [itemList['id'][0], vendorValue, TPSell, skinID]
    return commerceIDs



#Takes the base itemID, the recipeID to check the cost for, and then various dictionaries to reference
#Returns the cost of the recipe to craft and a list of recipes used to achieve that cost
def recursiveCost(itemID : int, recipeID : int, instantTP : bool, itemPriceInfo : dict, recipeList : dict, itemToRecipe : dict, itemList : dict, potentialRecipes : dict):
    #Check to see if we already covered this recipe in another call. If we have the crafting cost, just return that.
    if recipeID in potentialRecipes and potentialRecipes[recipeID][0] != False:
        return potentialRecipes[recipeID][0], potentialRecipes[recipeID][1]

    craftRecipes = set()
    craftCost = 0
    #Otherwise, we go through each ingredient in the recipe
    for ingredient in recipeList[recipeID][0]:
        id = ingredient[0]
        #"Cost" for the given item is not included. We have too much of it, we need to get rid of it
        if id == itemID or ingredient[2] != "Item":
            continue

        #If there are no recipes to -make- the item, then it must be a base material that we need to buy from the trading post (or some other place)
        #Add on t
        if not itemToRecipe[id][1]:
            thisCost = 0
            if instantTP:
                thisCost = (itemPriceInfo[id][1] * ingredient[1])
            else:
                thisCost = ((itemPriceInfo[id][0] + 1) * ingredient[1])
            craftCost += thisCost
            continue

        #Otherwise, there's a recipe to go down
        #Cost will be initialized based on user preference
        ingredientCost = 0
        if instantTP:
            ingredientCost = itemPriceInfo[id][1] * ingredient[1]
        else:
            ingredientCost = (itemPriceInfo[id][0] + 1) * ingredient[1]
        lowestID = False
        lowestRecipes = []
        
        #Grab an intersection of all items that make this ingredient AND any potential recipes. Covers cases like Prismatium Ingot
        ingRecipes = itemToRecipe[id][1]
        recipeUnion = ingRecipes & set(potentialRecipes.keys())
        #If there are similarities...
        if len(recipeUnion) > 0:
            ingRecipes = recipeUnion

        for secondRecipe in ingRecipes:
            compareCost, comparePrice, compareRecipes = recursiveCost(itemID, secondRecipe, instantTP, itemPriceInfo, recipeList, itemToRecipe, itemList, potentialRecipes)
            #If recipe output is LESS than the required amount for the parent recipe, multiply it until it matches
            if recipeList[secondRecipe][1][1] < ingredient[1]:
                multVal = math.ceil(ingredient[1] / recipeList[secondRecipe][1][1])
                compareCost *= multVal
            #If cost is lowest, this recipe for this ingredient is the most efficient
            #So we store the recipeID of that recipe, 
            if compareCost < ingredientCost:
                ingredientCost = compareCost
                lowestID = secondRecipe
                lowestRecipes = compareRecipes
        
        craftCost += ingredientCost
        if lowestID:
            craftRecipes.add(lowestID)
            craftRecipes |= lowestRecipes

    if recipeID in potentialRecipes:
        potentialRecipes[recipeID][0] = craftCost
        potentialRecipes[recipeID][1] = craftRecipes

    return craftCost, craftRecipes



#Helper function to take in a coin value and return a string formatted correctly
def printCost(value : int) -> str:
    if abs(value) < 100:
        return str(value) + "c"
    elif abs(value) < 10000:
        s = math.floor(value / 100)
        return str(s) + "s, " + str(abs(value) % 100) + "c"
    else:
        g = math.floor(value / 10000)
        sVal = abs(value) % 10000
        s = math.floor(sVal / 100)
        sVal = sVal % 100
        return str(g) + "g, " + str(s) + "s, " + str(sVal) + "c"



def updateSkinAPI(itemList : dict) -> set:
    while True:
        input = ("\nWould you like to prioritize crafting skins you do not have? To do this, we will need an API key with access to your 'Unlocks'.\n" + 
                 "Paste your API key here. If you do not want this, leave the space empty and press enter : ")
        if not input:
            itemList['skins'] = False
            return set()

        skinResponse = APICall('account/skins?access_token=', input.strip(), ignore = True)
        if type(skinResponse) is not int:
            itemList['skins'] = True
            itemList['API'] = input.strip()
            return set(skinResponse)
        


def updateItemList(itemList : dict, response : requests.Response = None) -> list:
    if response is None:
        response = APICall('items-names', '.json', link = 'https://api.gw2tp.com/1/bulk/')
        response = response['items']

    addedItems = []
    point = -1
    index = response[point]
    while index[0] not in itemList:
        itemList[index[0]] = [index[1], None, None, None]
        addedItems.append(index[0])
        point -= 1
        index = response[point]
    return addedItems



def grabSkinInfo(itemList : dict) -> set:
    skinResponse = APICall('account/skins?access_token=', itemList['API'], ignore = True)
    if skinResponse == 403:
        print("It appears that the key provided was not valid or did not have the necessary permissions. Please ensure your key is updated.")
        return updateSkinAPI(itemList)
    return set(skinResponse)



def readFile():
    pass



def writeFile(itemList : dict, recipeList : dict = None, itemToRecipe : dict = None):
    pass



def main():
    #Init
    response = APICall('items-names', '.json', link = 'https://api.gw2tp.com/1/bulk/')
    response = response['items']
    print("Welcome to the Item Crafting Checker! This will see if it is more profitable to craft something with those pesky items, or if you should just sell them!\n")

    toCheckItems = []
    skinSet = set()

    #Create/Maintain the file. It is a dictionary of IDs matched to names and a vendor value. What we grab from the API is a list.
    try:
        file = open("itemList.pickle", "rb")
        itemList = pickle.load(file)
        if response[-1][0] not in itemList:
            print("One moment while we update the stored items...")
            toCheckItems.extend(updateItemList(itemList, response))
        if itemList['recipe']:
            try:
                recipeList = pickle.load(file)
                itemToRecipe = pickle.load(file)
            except:
                recipeList = {}
                itemToRecipe = {}
        #If we should prioritize fashion, grab the list of unlocked skins from the API since it has likely changed since last time
        if itemList['skins']:
            skinSet = grabSkinInfo(itemList)
        file.close()
                
    #Create the file if it doesn't exist
    except OSError:
        print("Looks like there's not a stored list of items! \nOne moment while we create this list. It may take a second...\n")
        file = open("itemList.pickle", "wb")
        itemList = {}
        toCheckItems.extend(updateItemList(itemList, response))
        #The recipe list is accumulated, not initialized. There is too much information to grab and also some auxillary information i.e output name and ingredient names.
        input = ("Item list complete! Would you like to also store recipe information?\n" + 
                 "This is HIGHLY recommended. The program will take up more space, but will allow you to use the program more often without being locked out by the GW2 API.\n" + 
                 "Note: These lists are accumulated. The program may run slow at first, but will rapidly speed up as it gathers more recipe information.\nType yes/no : ")
        if input.lower() == 'yes' or input.lower() == 'y':
            itemList['recipe'] = True
        else:
            itemList['recipe'] = False
        skinSet = updateSkinAPI(itemList)
        pickle.dump(itemList, file)
        file.close()

    
    #Start the while loop that will run until the user exits the program
    while True:
        #Get user input for the item. Bug them until they give us something we can use
        while success := False != True:
            item = input("To exit the program, please type 'exit'. If you believe some cached recipe or item data may be incorrect, type 'clear'\n" + 
                         "If you would like to work through the cached items and update their info, type 'cache'\n" + 
                         "\t(Note: The only benefit will be linking skin IDs to items and minor improvements during the commerce section)\n" + 
                         "Which item do you want to search for? (This is case sensitive, type it as it appears in-game): ")
            item = item.strip().lower()
            if item == 'exit':
                print("\n\nClearing out cache first. Please do not exit the program, or the accumulated information will not be saved.\n")
                itemAPICall(toCheckItems, itemList)
                print("\n\nNow saving...\n")
                exit(0)
            elif item == 'clear':
                recipeList = {}
                itemToRecipe = {}
                haveSkins = itemList['skins']
                storeRecipes = itemList['recipe']
                itemList = {}
                updateItemList(itemList)
                itemList['skins'] = haveSkins
                itemList['recipe'] = storeRecipes

            elif item == 'cache':
                itemAPICall(toCheckItems, itemList)

            #We loop through the inital item list in order to grab the item ID. We must do a slow search like this since all internal / server code uses item IDs, not names.
            #I did not think it was worth storing a reversed dictionary -just- for this single part of the code.
            else:
                for pair in response:
                    if item == pair[1]:
                        itemID = str(pair[0])
                        success = True
                        break
                if not success:
                    print("Sorry, it doesn't look like that item is in our list.")
                    itemID = input("Do you know the ID of the item? This can be found on the Guild Wars 2 Wiki as the API listing (i.e 46742)\n" 
                                   + "If you don't know the ID or wish to try again, press Enter : ")
                    if itemID:
                        itemInfo = APICall('items/', itemID, True)
                        if type(itemInfo) is not int:
                            success = True
                        else:
                            print("Could not find that ID. Try the name again.")

        instantTP = True
        while True:
            resp = input("ID found! Would you like to sort the result by instant sell/buy and prefer it in cost calculations? (No will sort / prefer them by listing instead) [y/n]: ")
            if resp.lower() == 'y':
                break
            elif resp.lower() == 'n':
                instantTP = False
                break
            else:
                print("Response not recognized. Please respond with just the letter 'y' or 'n'\n")

        

        ##########################################################################################################################################
        #We now have the itemID and itemInfo from the item itself, so we need to gather all the recipes that USE that item
        if itemID not in itemToRecipe:
            itemToRecipe[itemID] = [None, None]

        potentialRecipes = {}
        recipesToCheck = [itemID]
        #Keep going until we reach every recipe that has ingredients stemming from the given ID
        while not recipesToCheck:
            idsToCheck = []
            #For every ID we have, we need to grab the recipes that use it as an ingredient
            for id in recipesToCheck:
                if id in itemToRecipe and itemToRecipe[id][0] != None:
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
                    if id in itemToRecipe:
                        itemToRecipe[id] = [set(recipeOutput), itemToRecipe[id][1]]
                    else:
                        itemToRecipe[id] = [set(recipeOutput), None]
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
                returnDict, returnIDs = recipeAPICall(unknownRecipeIDs)
                recipeList.update(returnDict)
                recipesToCheck.extend(returnIDs)

        del recipesToCheck
        
        #After the loop, we've gone up through every recipe! We have all the potential recipes, recipe info, and item info, so time to return it!
        ##########################################################################################################################################


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
                            
        
        ##########################################################################################################################################
        #Now that we have all the potential recipes, we need to start working back DOWN and grabbing all of the crafting costs
        #We start by, sadly, going through the recipes we don't know. We make as many API calls as we can at this point to get it out of the way
        print("Beginning recipe accumulation. This may take a moment depending on how many recipes have been stored, if that option was selected.")
        
        #For every recipe ID in potentialRecipes we need to look at the ingredients
        #See if we already have the recipe IDs to make the item. If not, API call
        #After each loop, gather all recipe IDs that we need to search for and do an API call
        #Gather info on recipes and then repeat until no more recipes are available
        nonItemInfo = []
        toFindInfo = [itemID]
        IDList = potentialRecipes.keys()
        #Items that we don't need to check other recipes for since they all use the required ingredient at -some- point
        essentialIDs = set()
        for id in IDList:
            outputItem = recipeList[id][1][0]
            essentialIDs.add(outputItem)
            toFindInfo.append(outputItem)
        while True:
            checkRecipeList = []
            unknownRecipes = []
            #For every recipe, go through the ingredients
            for recipeID in IDList:
                #If we don't have the recipe info, we will make a batch call at the end and re-investigate afterwards
                if recipeID not in recipeList:
                    unknownRecipes.append(recipeID)
                else:
                    for ingrd in recipeList[recipeID][0]:
                        #If it's not an item, add it to a separate. Otherwise, add it to the cost-checking for later
                        if ingrd[2] != 'Item': 
                            if ingrd[2] == "Currency":
                                nonItemInfo.append(ingrd[0])

                        thisIngredient = ingrd[0]
                        toFindInfo.append(thisIngredient)
                        #We do not need to look at or touch any recipes that make the 'essential items': items that have the -required- ingredient somewhere down the chain
                        if thisIngredient in essentialIDs: 
                            continue

                        #THEN see if we have the recipes to MAKE that ingredient. If not, API call!
                        if thisIngredient in itemToRecipe and itemToRecipe[thisIngredient][1] != None:
                            checkRecipeList.append(itemToRecipe[thisIngredient][1])
                        else:
                            #This is only one API call... but oh my god. We have to do it individually. We cannot group up IDs. This alone will cause so many slow downs :C
                            outputIDs = set(APICall('recipes/search?output=', thisIngredient))
                            if thisIngredient in itemToRecipe:
                                itemToRecipe[thisIngredient] = [itemToRecipe[thisIngredient][0], outputIDs]
                            else:
                                itemToRecipe[thisIngredient] = [None, outputIDs]
                            checkRecipeList.extend(outputIDs)

            #Work through the other recipe lists, down the chain
            IDList = checkRecipeList
            if not IDList:
                #If we've gone through all recipes to check AND we don't have any pending recipes, then we can leave
                if not unknownRecipes:
                    break
                else:
                    #Otherwise we churn through the unknown recipes, gathering info from them, and add them to the queue again to reinvestigate
                    returnDict, returnIDs = recipeAPICall(unknownRecipes)
                    recipeList.update(returnDict)
                    IDList = returnIDs

        #Go through the recipes and collect info on the non-item ingredients (currencies)
        #currencyDict = ID : name
        currencyDict = {}

        while nonItemInfo:
            strID = truncate(nonItemInfo)
            outputInfo = APICall('currencies?ids=', strID)
            for response in outputInfo:
                currencyDict[response['id']] = response['name']

        del nonItemInfo
        del IDList
        del essentialIDs
            
        
        #After the loop, we have all the recipe-related API calls done. 
        #########################################################################################################################################

        print("Now starting the trading post cost accumulation!")
        #Now we need to start calculating the cost of everything, churning through it all
        #itemPriceInfo = ID : [buyCost, sellCost]
        itemPriceInfo = {}

        #Some items will already have their accountbound / soulbound status and vendor value stored in the itemList dictionary
        #The others we will need to ping '/items' and -then- the commerce info
        # itemList = ID : [name, can be sold on TP?, vendor value, default skin]
        APIcommerceIDs = []
        APIitemIDs = []
        for potentialID in toFindInfo:
            #If we have the item info already...
            if potentialID in itemList and itemList[potentialID][1] != None:
                #Throw it into the 'commerce' bucket. Then check to see if we have the max number of IDs
                APIcommerceIDs.append(potentialID)
            #Otherwise, we will throw it into the 'grab item info' pile
            else:
                APIitemIDs.append(potentialID)
                #Once we can make a max-length call, do so
                if len(APIitemIDs) == 200:
                    APIcommerceIDs.extend(itemAPICall(APIitemIDs, itemList))
        #Finally, clear out the lists one last time to get any remaining IDs
        APIcommerceIDs.extend(itemAPICall(APIitemIDs, itemList))
        itemPriceInfo.update(commerceAPICall(APIcommerceIDs))

        del toFindInfo
        del APIcommerceIDs
        del APIitemIDs


        print("Final recipe cost accumulation running...")
        #Recursion is the easiest choice here. Looks a bit odd, but given python's whole 'pass-by-reference', we'll be good on space
        #recipeProfit = [[ID, profitBuy, profitSell], ...]
        recipeProfit = []
        skinRecipes = []
        noSellIDs = []

        #While looping through, keep track of the
        for recipeID in potentialRecipes:
            compareCost = recursiveCost(itemID, recipeID, instantTP, itemPriceInfo, recipeList, itemToRecipe, itemList, potentialRecipes)[0]
            outputID = recipeList[recipeID][0][1]

            #If we want to check for skins, then do so now (also making sure the output has a skin)
            if itemList['skins']:
                defaultSkin = itemList[outputID][3]
                if defaultSkin and defaultSkin not in skinSet:
                    skinRecipes.append(recipeID)

            #If the output item can be sold on the TP, grab the profit from selling (both instant sell and listing)
            if itemList[outputID][1]:
                profitBuy = (itemPriceInfo[outputID][0] * 0.85) - compareCost
                profitSell = (itemPriceInfo[outputID][1] * 0.85) - compareCost
                recipeProfit.append([recipeID, profitBuy, profitSell])
            #If it can only be vendor sold, we want to mark that
            elif itemList[outputID][2]:
                profitSell = itemList[outputID][2] - compareCost
                recipeProfit.append([recipeID, False, profitSell])
            #If it can't be sold at all, we need to remove it from the final print
            else:
                noSellIDs.append(recipeID)
        
        for recipeID in noSellIDs:
            potentialRecipes.pop(recipeID)
        del noSellIDs
            

        #########################################################################################################################################
        
        #All info has been gathered. Now to print it in a pretty format!
        print("API calls, comparisons, and calculations are done!!\n")
        #If we care about unlocked skins, do those first
        if skinRecipes:
            print("First, we found a couple of recipes that make skins you don't own! These are:")
            for recipeID in skinRecipes:
                itemName = itemList[    recipeList[recipeID][1][0]  ][0]
                print("\t" + itemName + ", which can be crafted for: \t" + potentialRecipes[recipeID][0])
            print("\n")

        #Now sort and also print the relevant reminder
        if instantTP:
            recipeProfit.sort(reverse=True, key=lambda x: x[1])
            print("Sorted by their profit if you were to instant sell the resulting item, they are:")
        else:
            recipeProfit.sort(reverse=True, key=lambda x: x[2])
            print("Sorted by their profit if you were to list the resulting item, they are:")
        
        #Only print recipes that we can sell for, even if its at a loss
        for recipeInfo in recipeProfit:
            peakRecipeID = recipeInfo[0]
            outputID = recipeList[peakRecipeID][1][0]
            #Plaintext name, NOT ID anymore since we need to print stuff all nice
            outputName = itemList[outputID][0]
            #Print a line with the name in the middle to clearly separate items
            print(outputName.center(40, '-'))
            #Print discipline and rating requirements
            print("Requires a level " + str(recipeList[peakRecipeID][2][1]) + " " + str(recipeList[peakRecipeID][2][0]))
            if recipeInfo[1] is False:
                print("Cannot be sold on the Trading Post. It can be sold to a vendor for " + printCost(itemList[outputID][2]) + " and a profit of " + printCost(recipeInfo[2]) + "\n")
            else:
                print("Instant sells for " + printCost(itemPriceInfo[outputID][0]) + " and a profit of " + printCost(recipeInfo[1]))
                print("Lists for " + printCost(itemPriceInfo[outputID][1]) + " and a profit of " + printCost(recipeInfo[2]) +"\n")
            print(outputName)

            #I did a large-arg recursion once. This one would be even worse. I tried. It needed ~10 args on my initial pass, without completing the code
            #So we're doing a custom interation method yippeeee
            #itemIDStack = [[itemID, tabIndent, parentRecipe], ...]
            itemIDStack = []
            for ingredient in recipeList[peakRecipeID][0]:
                itemIDStack.append([ingredient[0], 1, peakRecipeID])

            while itemIDStack:
                #Grab top of stack and sort relevant info
                currInfo = itemIDStack.pop()
                parentRecipeID = currInfo[2]
                currIndent = currInfo[1]
                currItem = currInfo[0]
                
                #Grab info on the ingredient so we know the type + quantity
                ingredientInfo = []
                for ing in recipeList[parentRecipeID][0]:
                    if ing[0] == currItem:
                        ingredientInfo = ing
                
                #Currencies get printed. They have no recipes or costs so they're quick and easy
                if ingredientInfo[2] == 'Currency':
                    currName = currencyDict[currItem]
                    print("\t" * currIndent + str(ingredientInfo[1]) + " " + currName)
                    continue

                currName = itemList[currItem][0]
                #Format: \t's + num of ingredients + name of ingredient (then, if base ingredient) - cost of ingredient on TP
                #i.e \t\t 5 Mithril Ore - 30c
                print("\t" * currIndent + str(ingredientInfo[1]) + " " + currName, end = "")
                nextRecipe : set = itemToRecipe[currItem][1] & potentialRecipes[peakRecipeID][1]

                #If none of the recipes to make the item are in the potentialRecipes bookkeeping...
                #That means that the cost to craft the item is GREATER than simply buying it off the TP
                #So, tell the user to buy it off the TP
                if not nextRecipe:
                    cost = 0
                    if instantTP:
                        cost = itemPriceInfo[currItem][1]
                    else:
                        cost = itemPriceInfo[currItem][0]
                    print(" - Buy off Trading Post for " + printCost(cost))
                    continue

                #Print statement to add a newline
                print("")
                #Otherwise, there's a recipe to use, so add it to the stack (error in case something goes wrong?)
                if len(nextRecipe) > 1:
                    raise Exception("nextRecipe has multiple values. We somehow have two recipes to make one item that are the lowest?")
                
                #Add all of the ingredients for the found recipe to the stack with a larger indent
                nextParent = nextRecipe.pop()
                for ingredient in recipeList[nextParent][0]:
                    itemIDStack.append([ingredient[0], currIndent + 1, nextParent])

            #After printing the crafting tree, newline to separate different items even more
            print("\n")
        
        input("All items have been printed! Press Enter when you are ready to continue...")



        

        
        







if __name__ == "__main__":
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

# FOR THE API!! 200 IDS IS THE LIMIT

# The most profitable item is:
# Recipe name (output) - Sells for this much on the TP
# 	Material 1 - Costs this much to craft / acquire on the TP
# 		If craft, more materials
#	Material 2 - TP
#	Material 3 - Currency
# Repeat per profitable recipe in descending order


# SAVED INFO

# itemList = ID : [name, can be sold on TP?, vendor value, default skin]
#	SPECIAL
#		ItemList['recipe'] = RecipeList exists?
#		ItemList['skins'] = SkinSet exists?
# recipeList = Recipe ID : [[list of ingredient IDs, quantity, type], [output ID, quantity], [discipline, rating]]
# itemToRecipe = Item ID : [{list of recipe IDs that use the item}, {list of recipe IDs that make the item}]

# PER - RUN INFO

# skinSet = set of unlocked skins
# itemPriceInfo = ID : [buyCost, sellCost]
# potentialRecipes = ID : craftCost, [recipes that make ingredients]
#   Notes: potentialRecipes keeps track of the total cost for that recipe, using the cheapest options on all lower branches.
#   It will be initialized with every possible recipe. As we work up, cull the more expensive recipes out from the second array
# currencyDict = ID : name
# itemCraftCost = ID : craftCost
# recipeProfit = [[ID, profitBuy, profitSell], ...]

# IF NOT STORING RECIPES
# recipeList and itemToRecipe are just variables

# outputList = [recipe IDs sorted by profit]
#	From the IDs, we can grab output ID / names, discipline / rating, and then list all materials + whether to craft or buy