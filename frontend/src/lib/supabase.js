import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

export const supabase = createClient(supabaseUrl, supabaseKey)

export async function checkSupabaseConnection() {
    const response = await fetch(`${supabaseUrl.replace(/\/$/, '')}/auth/v1/settings`, {
        headers: {
            apikey: supabaseKey,
            authorization: `Bearer ${supabaseKey}`,
        },
    })

    if (!response.ok) {
        throw new Error(`Supabase request failed with status ${response.status}`)
    }

    return response.json()
}