0.1 TOS_COM
    Send commands
        xx1     tos mode1
    Verify Telemetry
            xt4: state :: Cnt mission mode := yo_mode1 
            xx3: state :: Cnt active mode := cos_mode1 
            xx2: state :: Cnt running mode := mo_mode1 
            xz1: state :: Cnt mission mode := tos_mode3 
            xx2: state :: Cnt stole mode := tos_mode2 
        
        END