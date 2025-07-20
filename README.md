# IDEA-Helsinki
Repository for the IDEA Helsinki application developed for the TFDS-project. 

**ADD: Backsotry = "why-when-where", Project stakeholders, credits for the IDEA algorithm etc.**

## General configuration info

In it's current form, most of the configuration is done through the **constants** files:
- [Constants](/lib/Constants/Constants.py)
- [PrivateConstants](/lib/Constants/PrivateConstantExample.py)

## Program process schematic

*Copy pasted from [program_schematic](/docs/program_schematic.md)*

```mermaid
graph
    subgraph azureStorage["AZURE FCD blob storage"]
        TomTomBlobContainer("Tom Tom FCD container"):::db_bucket
    end
    
    subgraph TrafficDisturbanceWFS["Traffic Disturbance WFS service"]
        RoadWorks("Planned roadworks")
    end
    
    subgraph DisturbanceManager["Traffic disturbance manager"]
        TrafficDisturbanceDataRequest("Traffic disturbance data request handling")
        TrafficDisturbanceValidation("Traffic disturbance validation<br>'What disturbances can be validated based on date <br>(based on available FCD history [> 6 months]'")
        IntersectionDetection("Traffic disturbance - FCD<br>intersection detection")
        TrafficDisturbanceFCDDataProcessing("Traffic disturbance - FCD segments intersection data processing")
    end
    
    subgraph FcdManager["FCD manager"]
        FcdDataRequest("FCD data query handling")
        FcdDataModelProcessing("FCD data model processing")
        FcdDataMapProcessing("FCD segment map processing")
        FcdDataInfluxProcessing("FCD data model InfluxDB processing")
    end
    
    subgraph InfluxDB["Influx Data Base"]
        FcdBucket("FCD bucket"):::db_bucket 
        IdeaBucket("IDEA validation bucket"):::db_bucket
    end
    
    subgraph LocalStorage["Local storage"]
        FcdMapping("FCD segment mapping<br> - FCD segment mapping data model -"):::local_storage
        FcdMappingMasterHistory("FCD segment mapping history Master file"):::local_storage
        FcdMappingArchiveHistory("FCD segment mapping history archive file"):::local_storage 
        TrafficDisturbanceFCDData("Traffic disturbance - FCD segments intersection data<br> - Traffic disturbance data model -"):::local_storage
    end
    
    subgraph IdeaHelsinki["IDEA Helsinki"]
        IdeaManager("IDEA worker manager"):::idea_manager
        IdeaWorker("IDEA workers<br>'independent segment profiling and validation'"):::idea_worker
    end
    
    subgraph RoadSegmentState["Road segments current state"]
        
    end
    
    
    %% FCD processing
    TomTomBlobContainer -- "Raw Tom Tom fcd data" --> FcdDataRequest
    FcdDataRequest --> FcdDataModelProcessing
    FcdDataModelProcessing -- "Segment geometry" --> FcdDataMapProcessing
    FcdDataMapProcessing -- "Update current segment geometry" --> FcdMapping
    FcdMappingMasterHistory -- "Compare current segment geometry with records" --> FcdDataMapProcessing
    FcdDataMapProcessing -- "Update records if current segment geometry has changed" --> FcdMappingMasterHistory 
    FcdDataMapProcessing  --"Archive Segments not in current state" --> FcdMappingArchiveHistory
    
    FcdDataModelProcessing -- "Segment timeseries" --> FcdDataInfluxProcessing
    FcdDataInfluxProcessing -- "Update segment timeseries" --> FcdBucket
    
    %% Traffic disturbance processing
    RoadWorks -- "Raw traffic disturbance data" --> TrafficDisturbanceDataRequest
    TrafficDisturbanceDataRequest --> TrafficDisturbanceValidation
    TrafficDisturbanceValidation -- "Traffic disturbances that can be validated" -->IntersectionDetection
    FcdMapping -- "Current segment geometry" --> IntersectionDetection
    IntersectionDetection --> TrafficDisturbanceFCDDataProcessing
    TrafficDisturbanceFCDDataProcessing -- "Segments for validation" --> TrafficDisturbanceFCDData
    
    %% Idea processing
    TrafficDisturbanceFCDData -- "Get current state of validation targets" --> IdeaManager
    IdeaManager --"Create idea worker for each segment to be validated<br>Pass disturbance information" --> IdeaWorker
    FcdBucket -- "Get segment timeseries" --> IdeaWorker
    IdeaWorker --"update segment validation" --> IdeaBucket
    
    IdeaBucket -...-> RoadSegmentState
    
``` 

## Data models

Data models mentioned in the *Program process schematic*, are detailed in the [data models](/docs/data_models.md) documentation.

## Next steps in the development

1. Determine if data with geometry should be located in a database, instead of local storage.
   - Note that in Cloud deployment, *local storage* naturally is the default storage container provided.
2. 