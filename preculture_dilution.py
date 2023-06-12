from opentrons import protocol_api
import numpy as np
import pandas as pd

metadata = {'apiLevel': '2.13'}

plate_readings_file = "EmpyPlateTest.xls"

# desired values in target plate
target_OD = 0.05
target_volume = 150

rows = [chr(x) for x in range(ord("A"), ord("H")+1)] #letters from A to H
cols = list(range(12))

def process_OD_inputs():
    preculture_ODs = pd.read_excel(plate_readings_file, index_col=0, names=cols).loc[rows, cols].astype("float")

    if np.any(preculture_ODs < target_OD):
        print(f"Warning: At least one of the precultre ODs is below {target_OD} (OD)") 
    
    def get_transfer_volume(preculture_OD):
        """for a given preculture OD this returns the transfer volume in microL to obtain an OD of {@param target_OD} with a given {@param target_volume}"""
        transfer_volume = target_volume * target_OD / preculture_OD # volumen * wollen / haben
        return transfer_volume
    
    preculture_transfer_volumes = preculture_ODs.applymap(get_transfer_volume)

    media_tranfer_volumes = target_volume - preculture_transfer_volumes
    media_tranfer_volumes = media_tranfer_volumes.where(media_tranfer_volumes > 0, other=0)

    return preculture_transfer_volumes, media_tranfer_volumes

def run(protocol: protocol_api.ProtocolContext):
    # use raillights as sign of beeing active
    protocol.set_rail_lights(True)

    # load hardware
    preculture_wells = protocol.load_labware('corning_96_wellplate_360ul_flat', 2)
    target_wells = protocol.load_labware('corning_96_wellplate_360ul_flat', 1)
    media_wells = protocol.load_labware('corning_96_wellplate_360ul_flat', 4)

    tiprack20 = protocol.load_labware('opentrons_96_tiprack_20ul', 5)
    tiprack300 = protocol.load_labware('opentrons_96_tiprack_300ul', 3)

    pipette_p10 = protocol.load_instrument('p10_single', mount='left', tip_racks=[tiprack20]) # 1 - 10 µL
    pipette_p300 = protocol.load_instrument('p300_single', mount='right', tip_racks=[tiprack300]) # 30 - 300 µL

    p300_min_transfer_volume = 30
    p10_max_transfer_volume = 10 

    preculture_transfer_volumes, media_tranfer_volumes = process_OD_inputs()

    # opitmization:
    # first distribute media with large aspiration steps and without dropping the tip

    # second distribute preculture one by one


    # distribute medium

    if np.any(media_tranfer_volumes < p300_min_transfer_volume):
        # we need p10 for some steps
        pipette_p10.pick_up_tip()

    if np.any(media_tranfer_volumes >= p300_min_transfer_volume):
        # we can use p300 for some steps
        pipette_p300.pick_up_tip()

    for row in rows: # letters "A" - "H"
        for col in cols: # numbers 0-11
            
            media_volume = media_tranfer_volumes.loc[row, col]

            if media_volume <= 0:
                continue #nothing to transfer
                
            
            media_well = media_wells.rows_by_name()[row][col]
            target_well = target_wells.rows_by_name()[row][col]

            # select appropriate pipette
            pipette = pipette_p300 if media_volume >= p300_min_transfer_volume else pipette_p10
            
            # transfer without picking up or dropping a tip
            pipette.transfer(media_volume,
                                media_well,
                                target_well,
                                new_tip = "never") 
        
    #drop tips
    if pipette_p10.has_tip(): pipette_p10.drop_tip()
    if pipette_p300.has_tip(): pipette_p300.drop_tip()
    
    
    #transfer preculture
    for row in rows: # letters "A" - "H"
        for col in cols: # numbers 0-11
            
            preculture_volume = preculture_transfer_volumes.loc[row, col]

            if preculture_volume <= 0:
                continue #nothing to transfer
                
            
            target_well = target_wells.rows_by_name()[row][col]
            preculture_well = preculture_wells.rows_by_name()[row][col]

            # select appropriate pipette
            pipette = pipette_p300 if preculture_volume > p300_min_transfer_volume else pipette_p10
            
            # transfer preculture
            if preculture_volume > 0:
                pipette.transfer(preculture_volume,
                                 preculture_well,
                                 target_well,
                                 new_tip = "always")


    protocol.set_rail_lights(False) # signifies: done with protocol


if __name__ == "__main__":
    # simulate this protocol
    from opentrons import simulate
    with open(__file__) as f:
        logs = simulate.simulate(f, log_level="debug") # for less detail: coose higher level
    
    # save the logs
    cleaned_logs = ["{}: {}".format(log["payload"]["text"], log["payload"]) for log in logs[0]]
    with open("logs/preculture_dilution_logs.txt", "w+") as f:
        f.write("\n".join(cleaned_logs))
        