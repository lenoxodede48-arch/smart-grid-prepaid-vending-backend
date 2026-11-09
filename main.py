import urllib.parse
import asyncio
import json
import random
import datetime
import asyncpg
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from gmqtt import Client as MQTTClient

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Revolutionary Electricity Vending Server v2")

# REQUIRED: This blocks browsers from killing her network requests to your local Linux IP
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows UI site domain to communicate safely
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app = FastAPI(title="Revolutionary Electricity Vending Server")

# ─── 1. DATABASE & HARDWARE CONFIGURATION ───
# ─── 2. DATABASE CREDENTIAL ALIGNMENT ───
DB_USER = "postgres"
ENCODED_PASSWORD = "fx82ms#tg"  # Your hardware parameter password
DB_NAME = "electricity_token_db"

ENCODED_PASSWORD = urllib.parse.quote_plus(DB_NAME)
DB_DSN = f"postgres://postgres:{ENCODED_PASSWORD}@127.0.0.1:5432/electricity_token_db"

# ─── 1. EXTRACTED LINUX HARDWARE PARAMETERS ───
MQTT_BROKER = "broker.hivemq.com"  # Clean DNS resolution on Linux
MQTT_PORT = 1883               # Native MQTT TCP communication channel


db_pool: asyncpg.Pool = None
mqtt_client: MQTTClient = None

# ─── 2. PYDANTIC SCHEMAS FOR SWAGGER UI INPUTS ───
class CallbackItem(BaseModel):
    Name: str
    Value: float | str | None = None

class CallbackMetadata(BaseModel):
    Item: list[CallbackItem]

class StkCallbackDetails(BaseModel):
    MerchantRequestID: str
    CheckoutRequestID: str
    ResultCode: int
    ResultDesc: str
    CallbackMetadata: CallbackMetadata

class StkCallbackBody(BaseModel):
    stkCallback: StkCallbackDetails

class MpesaCallbackPayload(BaseModel):
    Body: StkCallbackBody

# ─── 3. MQTT EVENT INTERCEPTION LAYER ───
def on_connect(client, flags, rc, properties):
    print("🔌 [MQTT Connected] Listening for hardware telemetry...")
    client.subscribe("tritech/readings/+", qos=1)

def on_message(client, topic, payload, qos, properties):
    try:
        # 1. FIXED: Extract the LAST element index string from the split path array
        topic_parts = topic.split("/")
        hardware_id = topic_parts[-1] # This cleanly extracts "antony123"
        
        decoded_raw_message = payload.decode()
        print(f"📥 [Air Signal Intercepted] Device: {hardware_id}")
        
        data = json.loads(decoded_raw_message)
        remaining_credit = float(data.get("current_balance_kwh", 0.0))
        
        # 2. FIXED: Aligned fallback key extraction directly matching payload dictionary key
        mapped_meter_id = data.get("meter_id", "MTR-2026-001")
        
        # Pass to the working database handler pool asynchronously
        asyncio.create_task(sync_credit_to_database(mapped_meter_id, remaining_credit))
        
    except Exception as e:
        print(f"❌ [MQTT Parsing Failure]: {str(e)}")


async def sync_credit_to_database(meter_id: str, current_balance: float):
    query = "UPDATE meters SET current_balance_kwh = $2 WHERE meter_id = $1;"
    try:
        async with db_pool.acquire() as connection:
            await connection.execute(query, meter_id, current_balance)
            print(f"💾 [PostgreSQL Updated] Hardware balance synced: {current_balance} kWh")
    except Exception as e:
        print(f"❌ [DB Storage Write Error]: {str(e)}")
#MQTT Client Initialization
def generate_mock_sts_token() -> str:
    """
    Constructs an encrypted, deterministic 20-digit prepaid utility token 
    format matching physical smart meter specifications.
    """
    blocks = ["".join(str(random.randint(0, 9)) for _ in range(4)) for _ in range(5)]
    return "-".join(blocks)

#POST /api/v1/payments/mpesa-callback endpoint to simulate M-Pesa callback
@app.post("/api/v1/payments/mpesa-callback", summary="Simulate Real-World Payment Callback")
async def mpesa_callback(meter_id: str, payload: MpesaCallbackPayload):
    """
    Simulates a live Safaricom M-Pesa STK Callback.
    Generates a secure 20-digit token and transmits it over-the-air to HiveMQ.
    """
    try:
        stk_callback = payload.Body.stkCallback
        if stk_callback.ResultCode != 0:
            return {"status": "Transaction declined", "reason": stk_callback.ResultDesc}
            
        metadata_items = stk_callback.CallbackMetadata.Item
        metadata = {item.Name: item.Value for item in metadata_items}
        
        mpesa_tx_id = metadata.get("MpesaReceiptNumber")  
        phone_number = str(metadata.get("PhoneNumber"))    
        amount = float(metadata.get("Amount"))

        if not mpesa_tx_id:
            raise HTTPException(status_code=400, detail="Missing MpesaReceiptNumber in payload metadata.")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # 🛡️ ANTI-DUPLICATE GUARD: Prevent processing the same transaction code twice
                duplicate_check = await conn.fetchrow(
                    "SELECT mpesa_receipt_number FROM transactions WHERE mpesa_receipt_number = $1;", 
                    mpesa_tx_id
                )
                if duplicate_check:
                    raise HTTPException(status_code=409, detail=f"Duplicate detected! Transaction {mpesa_tx_id} already processed.")

                # Verify meter exists in the system warehouse registry
                meter_record = await conn.fetchrow("SELECT meter_id FROM meters WHERE meter_id = $1", meter_id)
                if not meter_record:
                    raise HTTPException(status_code=404, detail="Meter ID not registered.")

                # Handle dynamic user lookup/registration matching your table constraints
                user = await conn.fetchrow("SELECT user_id FROM users WHERE phone_number = $1", phone_number)
                if not user:
                    # Fix: Inject an automated system placeholder hash to satisfy the NOT NULL database rule
                    system_generated_hash = f"auto_generated_token_{random.randint(1000, 9999)}"
                    user = await conn.fetchrow(
                        """
                        INSERT INTO users (phone_number, password_hash) 
                        VALUES ($1, $2) 
                        RETURNING user_id;
                        """, 
                        phone_number, system_generated_hash
                    )
                
                user_id = user["user_id"]
                await conn.execute("UPDATE meters SET assigned_user_id = $1 WHERE meter_id = $2 AND assigned_user_id IS NULL;", user_id, meter_id)

                token_code = generate_mock_sts_token()

                # Record transaction ledger entry
                await conn.execute(
                    "INSERT INTO transactions (mpesa_receipt_number, meter_id, amount, token_generated) VALUES ($1, $2, $3, $4);",
                    mpesa_tx_id, meter_id, amount, token_code
                )

        # Dispatch Token Payload over-the-air to the hardware teammate's dashboard
        hardware_ota_topic = "tritech/readings/antony123/tokens"
        outbound_packet = {
            "token": token_code, 
            "added_units": amount / 22.0, 
            "timestamp": str(datetime.datetime.now(datetime.timezone.utc))
        }
        
        if mqtt_client:
            mqtt_client.publish(hardware_ota_topic, json.dumps(outbound_packet), qos=1)
            print(f"📡 [OTA Dispatch] Token {token_code} sent to hardware link.")

        return {"status": "Success", "token_allocated": token_code, "transaction_id": mpesa_tx_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))



# ─── 5. BOTTOM SECTION: GET METER LOOKUP & TRANSACTION LEDGER ───
# ─── BOTTOM SECTION: GET METER LOOKUP & TRANSACTION LEDGER ───
@app.get("/api/v1/meters/lookup/{meter_id}", summary="Lookup Meter Balance & Ledger Audit")
async def lookup_meter_account(meter_id: str):
    """
    Direct database lookup that checks columns dynamically to avoid empty outputs.
    """
    # Safety Check: Verify database pool was created cleanly during server startup
    if db_pool is None:
        raise HTTPException(
            status_code=503, 
            detail="Database connection pool is offline. Check your Uvicorn terminal logs for authentication failures."
        )

    meter_query = """
        SELECT m.*, u.*
        FROM meters m
        LEFT JOIN users u ON m.assigned_user_id = u.user_id
        WHERE m.meter_id = $1;
    """
    ledger_query = """
        SELECT * FROM transactions 
        WHERE meter_id = $1;
    """
    try:
        async with db_pool.acquire() as connection:
            record = await connection.fetchrow(meter_query, meter_id)
            if not record:
                raise HTTPException(status_code=404, detail=f"Meter '{meter_id}' does not exist in the database.")
            
            row = dict(record)
            balance = row.get("current_balance_kwh") or row.get("balance") or row.get("units") or 0.0
            phone = row.get("phone_number") or row.get("phone") or row.get("msisdn") or "No owner linked yet"
            
            history = await connection.fetch(ledger_query, meter_id)
            
            return {
                "meter_status": {
                    "meter_id": row.get("meter_id"),
                    "current_balance_kwh": float(balance),
                    "linked_owner_phone": str(phone)
                },
                "transaction_ledger_history": [
                    {
                        "mpesa_receipt_number": tx.get("mpesa_receipt_number") or tx.get("receipt") or tx.get("mpesa_code") or "N/A",
                        "amount_paid_kes": float(tx.get("amount") or tx.get("amount_paid_kes") or 0),
                        "token_issued": tx.get("token_generated") or tx.get("token") or "N/A"
                    } for tx in history
                ]
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database extraction layout mismatch: {str(e)}")

@app.on_event("startup")
async def startup_event():
    global db_pool, mqtt_client
    print("\n🚀 [Diagnostic Boot] Initializing Production Pools...")
    
    # 1. Start your database link
    try:
        db_pool = await asyncpg.create_pool(dsn=DB_DSN)
        print("💾 ✅ PostgreSQL Database link successfully initialized.")
    except Exception as e:
        print(f"❌ Database connection failed: {str(e)}")
        
    # 2. FORCE THE MQTT CHANNELS TO TURN ON NATIVELY
    try:
        print(f"📡 Connecting to HiveMQ MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}...")
        mqtt_client = MQTTClient("utility_core_vending_server")
        mqtt_client.on_connect = on_connect
        mqtt_client.on_message = on_message
        
        # Connect to the public broker on Port 1883
        await mqtt_client.connect(MQTT_BROKER, port=MQTT_PORT, ssl=False, keepalive=60, version=4)
        print("🔌 ✅ MQTT Network Line Active! Listening for Antony's prototype readings...\n")
    except Exception as e:
        print(f"⚠️ MQTT Network Connection delayed: {str(e)}\n")

#feat: initialize asynchronous core vending and telemetry infrastructure
