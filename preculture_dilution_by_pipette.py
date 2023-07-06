from opentrons import protocol_api
from opentrons.protocol_api import InstrumentContext, Labware, ProtocolContext
import numpy as np
import pandas as pd
from typing import Literal

metadata = {'apiLevel': '2.13'}

plate_readings_file = "PlateReadings.xls"

# desired values in target plate
target_OD = 0.05
target_volume = 150

rows = [chr(x) for x in range(ord("A"), ord("H")+1)] #letters from A to H
cols = list(range(12))


def get_transfer_volume(preculture_OD):
    """for a given preculture OD this returns the transfer volume in microL to obtain an OD of {@param target_OD} with a given {@param target_volume}"""
    transfer_volume = target_volume * target_OD / preculture_OD # volumen * wollen / haben
    return transfer_volume


def process_OD_inputs():
    preculture_ODs = pd.read_excel(plate_readings_file, index_col=0, names=cols).loc[rows, cols].astype("float")

    if np.any(preculture_ODs < 0):
        raise ValueError("preculture OD below 0")

    if np.any(preculture_ODs < target_OD):
        print(f"Warning: At least one of the precultre ODs is below {target_OD} (OD)") 
    
    preculture_transfer_volumes = preculture_ODs.applymap(get_transfer_volume)

    media_tranfer_volumes = target_volume - preculture_transfer_volumes
    media_tranfer_volumes = media_tranfer_volumes.where(media_tranfer_volumes > 0, other=0)

    return preculture_transfer_volumes, media_tranfer_volumes

def run(protocol: ProtocolContext):
    # use raillights as sign of beeing active
    protocol.set_rail_lights(True)

    # load hardware
    preculture_wells = protocol.load_labware('corning_96_wellplate_360ul_flat', 2)
    target_wells = protocol.load_labware('corning_96_wellplate_360ul_flat', 1)
    media_wells = protocol.load_labware('corning_96_wellplate_360ul_flat', 4)

    tiprack_20ul = protocol.load_labware('opentrons_96_tiprack_20ul', 5)
    tiprack_300ul = protocol.load_labware('opentrons_96_tiprack_300ul', 3)
    tiprack_300ul_2 = protocol.load_labware('opentrons_96_tiprack_300ul', 6)

    pipette_p10 = protocol.load_instrument('p10_single', mount='left', tip_racks=[tiprack_20ul]) # 1 - 10 µL
    pipette_p300 = protocol.load_instrument('p300_single', mount='right', tip_racks=[tiprack_300ul, tiprack_300ul_2]) # 30 - 300 µL

    p300_min_transfer_volume = 30

    preculture_transfer_volumes, media_tranfer_volumes = process_OD_inputs()

    # opitmization:
    # first distribute media with large aspiration steps and without dropping the tip

    # second distribute preculture one by one

    def transfer_to_target(volumes: pd.DataFrame, 
                            source_wells: Labware,
                            new_tip: Literal["never", "always"]
                            ):
        """
        transfer the given volums from the given source_wells to the targetwells
        new_tip = "never" will pick up one tip at the start if necessary
        and drop it at the end
        new_tip = "always" will pick up a new tip for every transfer
        """
        for pipette in [pipette_p10, pipette_p300]:
            if pipette == pipette_p10:
                pipette_applicable = lambda volume: 0 < volume <= p300_min_transfer_volume
            elif pipette == pipette_p300:
                pipette_applicable = lambda volume: p300_min_transfer_volume < volume
            
            if not np.any(pipette_applicable(volumes)):
                # pipette not applicable to any volume, 
                # proceeding to next pipette
                continue

            if new_tip == "never":
                pipette.pick_up_tip() #only pick up one tip at the start

            for row in rows: # letters "A" - "H"
                for col in cols: # numbers 0-11
                    
                    volume = volumes.loc[row, col]

                    if not pipette_applicable(volume):
                        # pipette not recommended for volume, other pipette will handle this
                        continue
                        
                    source = source_wells.rows_by_name()[row][col]
                    target = target_wells.rows_by_name()[row][col]

                    # transfer without picking up or dropping a tip
                    pipette.transfer(volume,
                                    source,
                                    target,
                                    new_tip = new_tip) 

            if pipette.has_tip: 
                pipette.drop_tip() 


    # transfer medium
    transfer_to_target(media_tranfer_volumes, media_wells, new_tip="never")

    # transfer preculture
    transfer_to_target(preculture_transfer_volumes, preculture_wells, new_tip="always")
    
    protocol.home()
    
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
        