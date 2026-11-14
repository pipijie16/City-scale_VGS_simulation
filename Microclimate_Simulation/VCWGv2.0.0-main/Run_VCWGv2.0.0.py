from VCWG_Hydrology import VCWG_Hydro

"""
Specify file and case names
Developed by Mohsen Moradi and Amir A. Aliabadi
Atmospheric Innovations Research (AIR) Laboratory, University of Guelph, Guelph, Canada
Last update: December 2020
"""
#Basel
'''
epwFileName = 'ERA5_Basel_Jun.epw'
TopForcingFileName = None
VCWGParamFileName = 'initialize_Basel_MOST.uwg'
ViewFactorFileName = 'ViewFactor_Basel_MOST.txt'
# Case name to append output file names with
case = 'Basel_MOST'
'''

#Wuhan
#'''
epwFileName = 'WuhanEPW.epw'
TopForcingFileName = None
VCWGParamFileName = 'initialize_Wuhan_LCZ1.uwg'
ViewFactorFileName = 'ViewFactor_Wuhan_LCZ1.txt'
# Case name to append output file names with
case = 'Wuhan_LCZ1'
#'''

# Initialize the UWG object and run the simulation
VCWG = VCWG_Hydro(epwFileName,TopForcingFileName,VCWGParamFileName,ViewFactorFileName,case)
VCWG.run()